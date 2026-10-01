"""Run the real engine, authenticated management adapter, and native HTTPS endpoint.

Service-compatible supervisor. It owns only the child processes it launches.
"""
import argparse
import importlib.util
import ipaddress
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

REPO = Path(__file__).resolve().parent.parent
WORK = REPO.parent


def appliance_runtime():
    spec = importlib.util.spec_from_file_location("appliance_runtime", REPO / "scripts/appliance-runtime.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def initialize(path):
    if path.exists():
        raise RuntimeError("Configuration already exists; refusing to replace engine secrets")
    path.parent.mkdir(parents=True, exist_ok=True)
    config = {"state_dir": str(path.parent / "state"),
              "php_executable": str(WORK / "php-runtime/php.exe"),
              "php_extension_dir": str(WORK / "php-runtime/ext"),
              "engine_cli": str(WORK / "multiotp-engine/multiotp.php"),
              "engine_class": str(WORK / "multiotp-engine/multiotp.class.php"),
              "adapter_token": secrets.token_urlsafe(40),
              "native_shared_secret": secrets.token_urlsafe(40),
              "auth_bind": "127.0.0.1", "auth_port": 18443, "adapter_port": 18090,
              "certificate_file": str(path.parent / "engine-cert.pem"),
              "certificate_key_file": str(path.parent / "engine-cert.key")}
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    Path(config["certificate_file"]).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    Path(config["certificate_key_file"]).write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    with path.open("x", encoding="utf-8") as stream:
        json.dump(config, stream, indent=2)
    for file in [path, Path(config["certificate_key_file"])]:
        try:
            file.chmod(0o600)
        except OSError:
            pass
    print(f"Initialized private engine configuration: {path}")


def serve(config, check=False, stop_file=None):
    for key in ["php_executable", "engine_cli", "engine_class", "certificate_file", "certificate_key_file"]:
        if not Path(config[key]).is_file():
            raise RuntimeError(f"Required file missing: {key}")
    state = Path(config["state_dir"])
    state.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(BLISS_ENGINE_CLASS=config["engine_class"], BLISS_ENGINE_STATE=str(state),
               BLISS_ENGINE_SHARED_SECRET=config["native_shared_secret"],
               BLISS_NATIVE_ROUTER=str(REPO / "deployment/engine-auth/router.php"),
               BLISS_PHP_CGI=str(Path(config["php_executable"]).with_name("php-cgi.exe")),
               BLISS_PHP_EXTENSIONS=config.get("php_extension_dir", ""),
               PYTHONPATH=str(REPO / "services/multiotp-adapter"))
    if not Path(env["BLISS_PHP_CGI"]).is_file():
        raise RuntimeError("PHP CGI runtime missing")
    ini = state.parent / "native-php.ini"
    extension_dir = str(Path(config["php_extension_dir"]).resolve()).replace("\\", "/")
    ini.write_text('extension_dir="' + extension_dir + '"\nextension=mbstring\nextension=openssl\n'
                   'cgi.force_redirect=1\ndisplay_errors=0\nlog_errors=0\nexpose_php=0\n', encoding="utf-8")
    env.update(PHPRC=str(ini), PHP_INI_SCAN_DIR="")
    adapter_env = os.environ.copy()
    adapter_env.update(PYTHONPATH=str(REPO / "services/multiotp-adapter"),
        MULTIOTP_EXECUTABLE=config["engine_cli"], MULTIOTP_PHP_EXECUTABLE=config["php_executable"],
        MULTIOTP_PHP_EXTENSION_DIR=config.get("php_extension_dir", ""), MULTIOTP_BASE_DIR=str(state),
        ADAPTER_SHARED_TOKEN=config["adapter_token"], ADAPTER_ENABLE_WRITES="true")
    extra, extra_checks = (appliance_runtime().processes(REPO, config, state.parent, sys.executable)
                           if (state.parent / "appliance.json").exists() else ([], []))
    processes = []
    logs = []
    stopping = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    try:
        for name, command, child_env in [
            ("native-auth", [sys.executable, "-m", "uvicorn", "adapter.native:app",
                             "--host", config["auth_bind"], "--port", str(config["auth_port"]),
                             "--ssl-certfile", config["certificate_file"],
                             "--ssl-keyfile", config["certificate_key_file"],
                             "--no-access-log", "--http", "h11", "--loop", "asyncio", "--limit-concurrency", "32",
                             "--timeout-keep-alive", "5"], env),
            ("adapter", [sys.executable, "-m", "uvicorn", "adapter.main:app", "--host", "127.0.0.1",
                         "--port", str(config["adapter_port"]), "--no-access-log"], adapter_env), *extra]:
            logfile = open(state.parent / (name + ".log"), "a", encoding="utf-8")  # noqa: SIM115
            logs.append(logfile)
            processes.append(subprocess.Popen(command, cwd=state.parent, env=child_env,
                                               stdout=logfile, stderr=logfile))
        for url, headers in [(f"https://127.0.0.1:{config['auth_port']}/health", {}),
                             (f"http://127.0.0.1:{config['adapter_port']}/health", {}), *extra_checks]:
            for _ in range(100):
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError("Engine component exited; inspect its private log")
                try:
                    if httpx.get(url, headers=headers, timeout=2, verify=config["certificate_file"] if url.startswith("https") else True, trust_env=False).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError("Engine startup timed out")

        print(f"Management API: http://127.0.0.1:{config['adapter_port']}/docs", flush=True)
        print(f"Native authentication: https://{config['auth_bind']}:{config['auth_port']}/auth", flush=True)
        print("Engine running. Ctrl+C stops only these owned components.", flush=True)
        if check:
            return
        while not stopping.wait(.5):
            if stop_file and stop_file.exists():
                stop_file.unlink()
                break
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("Engine component exited; stopping this engine instance")
    finally:
        for process in processes:
            if process.poll() is None:
                if os.name == 'nt':
                    # PHP-CGI is a child of the owned gateway; stop the entire
                    # owned tree before declaring a snapshot safe to take.
                    try:
                        subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       timeout=10, check=False)
                    except (OSError, subprocess.TimeoutExpired):
                        process.terminate()
                else:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        for logfile in logs:
            logfile.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=REPO / ".local/engine/config.json")
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--check", action="store_true", help="Start components, verify readiness, then stop them")
    parser.add_argument("--stop", action="store_true", help="Request graceful service shutdown")
    parser.add_argument("--initialize-appliance", action="store_true")
    parser.add_argument("--license-url")
    parser.add_argument("--public-key", type=Path)
    args = parser.parse_args()
    stop_file = args.config.resolve().with_suffix(".stop")
    if args.stop:
        stop_file.touch()
    elif args.initialize_appliance:
        if not args.license_url or not args.public_key:
            parser.error("Appliance setup requires --license-url and --public-key")
        appliance_runtime().initialize(args.config.resolve(), args.license_url, args.public_key.resolve())
    elif args.initialize:
        initialize(args.config.resolve())
    else:
        stop_file.unlink(missing_ok=True)
        serve(json.loads(args.config.read_text(encoding="utf-8-sig")), args.check, stop_file)
