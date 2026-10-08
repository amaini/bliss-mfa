import importlib.util
import json
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("appliance_runtime_env", SCRIPTS / "appliance-runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def test_api_env_has_engine_config_and_validation_dir(tmp_path):
    root = tmp_path / "root"
    repo = root / "bliss-mfa"
    (root / "node").mkdir(parents=True)
    (root / "node/node.exe").write_bytes(b"")
    (root / "portal").mkdir()
    (root / "portal/server.js").write_text("")
    state = repo / ".local/engine"
    state.mkdir(parents=True)
    (state / "appliance.json").write_text(json.dumps({
        "database_file": str(state / "a.db"), "jwt_secret": "j", "setup_token": "s", "company_name": "c",
        "agent_port": 1, "agent_token": "a", "api_port": 2, "portal_port": 3, "tls_port": 4,
        "license_url": "https://x", "public_key_file": "k", "license_state_dir": str(state)}))
    engine_config = {"adapter_port": 5, "adapter_token": "t", "certificate_file": "c", "certificate_key_file": "k"}
    procs = runtime.processes(repo, engine_config, state, "python")
    api = next(p[2] for p in procs if p[0] == "appliance-api")
    assert api["ENGINE_CONFIG_FILE"] == str(state / "config.json")
    assert api["PROVIDER_VALIDATION_DIR"] == str(root / "provider-validation")
