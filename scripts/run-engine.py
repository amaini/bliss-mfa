"""Run the real engine, authenticated management adapter, and native HTTPS endpoint.

Prototype foreground supervisor. It owns only the child processes it launches.
"""
import argparse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import ssl
import subprocess
import sys
import threading
import time

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

REPO = Path(__file__).resolve().parent.parent
WORK = REPO.parent


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


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


def serve(config, check=False):
    for key in ["php_executable", "engine_cli", "engine_class", "certificate_file", "certificate_key_file"]:
        if not Path(config[key]).is_file():
            raise RuntimeError(f"Required file missing: {key}")
    state = Path(config["state_dir"])
    state.mkdir(parents=True, exist_ok=True)
    php_port = free_port()
    php_args = [config["php_executable"]]
    if config.get("php_extension_dir"):
        php_args += ["-n", "-d", "extension_dir=" + config["php_extension_dir"],
                     "-d", "extension=mbstring", "-d", "extension=openssl"]
    env = os.environ.copy()
    env.update(BLISS_ENGINE_CLASS=config["engine_class"], BLISS_ENGINE_STATE=str(state),
               BLISS_ENGINE_SHARED_SECRET=config["native_shared_secret"])
    adapter_env = os.environ.copy()
    adapter_env.update(PYTHONPATH=str(REPO / "services/multiotp-adapter"),
        MULTIOTP_EXECUTABLE=config["engine_cli"], MULTIOTP_PHP_EXECUTABLE=config["php_executable"],
        MULTIOTP_PHP_EXTENSION_DIR=config.get("php_extension_dir", ""), MULTIOTP_BASE_DIR=str(state),
        ADAPTER_SHARED_TOKEN=config["adapter_token"], ADAPTER_ENABLE_WRITES="true")
    processes = []
    logs = []
    server = None
    stopping = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    try:
        for name, command, child_env in [
            ("native-auth", [*php_args, "-S", f"127.0.0.1:{php_port}",
                             str(REPO / "deployment/engine-auth/router.php")], env),
            ("adapter", [sys.executable, "-m", "uvicorn", "adapter.main:app", "--host", "127.0.0.1",
                         "--port", str(config["adapter_port"]), "--no-access-log"], adapter_env)]:
            logfile = open(state.parent / (name + ".log"), "a", encoding="utf-8")
            logs.append(logfile)
            processes.append(subprocess.Popen(command, cwd=state.parent, env=child_env,
                                               stdout=logfile, stderr=logfile))
        for child_port in [php_port, config["adapter_port"]]:
            for _ in range(100):
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError("Engine component exited; inspect its private log")
                try:
                    if httpx.get(f"http://127.0.0.1:{child_port}/health", timeout=.5).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError("Engine startup timed out")

        class AuthProxy(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                if self.path != "/auth":
                    self.send_error(404)
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self.send_error(400)
                    return
                if not 0 < size <= 65536:
                    self.send_error(413)
                    return
                self.connection.settimeout(10)
                try:
                    response = httpx.post(f"http://127.0.0.1:{php_port}/auth",
                        content=self.rfile.read(size), timeout=10,
                        headers={"Content-Type": "application/x-www-form-urlencoded"})
                    self.send_response(response.status_code)
                    self.send_header("Content-Type", "application/xml; charset=utf-8")
                    self.send_header("Content-Length", str(len(response.content)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(response.content)
                except (httpx.HTTPError, OSError):
                    self.send_error(503)

            def do_GET(self):
                self.send_error(404)

        server = ThreadingHTTPServer((config["auth_bind"], config["auth_port"]), AuthProxy)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(config["certificate_file"], config["certificate_key_file"])
        server.socket = context.wrap_socket(server.socket, server_side=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f"Management API: http://127.0.0.1:{config['adapter_port']}/docs", flush=True)
        print(f"Native authentication: https://{config['auth_bind']}:{config['auth_port']}/auth", flush=True)
        print("Engine running. Ctrl+C stops only these owned components.", flush=True)
        if check:
            return
        while not stopping.wait(.5):
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("Engine component exited; stopping this engine instance")
    finally:
        if server:
            server.shutdown()
            server.server_close()
        for process in processes:
            if process.poll() is None:
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
    args = parser.parse_args()
    if args.initialize:
        initialize(args.config.resolve())
    else:
        serve(json.loads(args.config.read_text(encoding="utf-8")), args.check)
