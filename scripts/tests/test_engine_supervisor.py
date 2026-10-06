"""The authentication core must survive every management/commercial component failure."""
import socket
import sys
import time
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import engine_supervisor as supervision  # noqa: E402

SERVER = '''
import http.server, sys
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
    def log_message(self, *args):
        pass
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
'''
MANAGEMENT = ('portal', 'license-agent', 'appliance-api', 'portal-tls')


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def server(name, critical, command=None):
    port = free_port()
    return supervision.Component(
        name=name, critical=critical, env=None,
        command=command or [sys.executable, '-c', SERVER, str(port)],
        health=(f'http://127.0.0.1:{port}/health', {}))


def until(supervisor, condition, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        supervisor.poll()
        if condition():
            return
        time.sleep(.05)
    raise AssertionError('condition not reached')


def auth_ok(component):
    url = component.health[0].replace('/health', '/auth')
    return httpx.get(url, timeout=2, trust_env=False).status_code == 200


@pytest.fixture
def stack(tmp_path):
    started = []

    def build(management=None, **options):
        auth = server('native-auth', True)
        adapter = server('adapter', True)
        components = [auth, adapter, *(management or [server(name, False) for name in MANAGEMENT])]
        options.setdefault('backoff_initial', .05)
        options.setdefault('backoff_max', .2)
        supervisor = supervision.Supervisor(components, cwd=tmp_path, log_dir=tmp_path, **options)
        started.append(supervisor)
        return supervisor, auth, adapter

    yield build
    for supervisor in started:
        supervisor.stop()


@pytest.mark.parametrize('name', MANAGEMENT)
def test_management_crash_does_not_stop_auth(stack, name):
    supervisor, auth, adapter = stack()
    supervisor.start()
    core = {n: supervisor.pid(n) for n in ('native-auth', 'adapter')}
    crashed = supervisor.pid(name)
    supervisor.kill(name)

    until(supervisor, lambda: supervisor.pid(name) not in (None, crashed))

    assert {n: supervisor.pid(n) for n in core} == core
    assert supervisor.alive('native-auth') and supervisor.alive('adapter')
    assert auth_ok(auth)


def test_existing_auth_continues_while_all_management_is_down(stack):
    failing = [supervision.Component(name=name, critical=False, env=None,
                                     command=[sys.executable, '-c', 'raise SystemExit(3)'])
               for name in MANAGEMENT]
    supervisor, auth, _ = stack(failing)
    supervisor.start()
    for _ in range(20):
        supervisor.poll()
        assert auth_ok(auth)
        time.sleep(.05)
    assert all(supervisor.failures(name) >= 1 for name in MANAGEMENT)


def test_unreachable_licensing_server_does_not_stop_auth(stack):
    # The agent's outbound connection fails; whatever it does next, auth is unaffected.
    agent = supervision.Component(name='license-agent', critical=False, env=None, command=[
        sys.executable, '-c',
        'import socket,sys\ntry: socket.create_connection(("127.0.0.1", 9), timeout=1)\n'
        'except OSError: sys.exit(1)'])
    supervisor, auth, _ = stack([agent])
    supervisor.start()
    until(supervisor, lambda: supervisor.failures('license-agent') >= 2)
    assert supervisor.alive('native-auth')
    assert auth_ok(auth)


def test_startup_does_not_wait_for_management_readiness(stack):
    never_ready = supervision.Component(
        name='portal', critical=False, env=None, command=[sys.executable, '-c', 'import time; time.sleep(60)'],
        health=(f'http://127.0.0.1:{free_port()}/health', {}))
    supervisor, auth, _ = stack([never_ready], ready_timeout=1)
    supervisor.start()
    assert auth_ok(auth)


def test_preflight_check_still_requires_management_readiness(stack):
    broken = supervision.Component(name='appliance-api', critical=False, env=None,
                                   command=[sys.executable, '-c', 'raise SystemExit(1)'],
                                   health=(f'http://127.0.0.1:{free_port()}/health', {}))
    supervisor, _, _ = stack([broken], ready_timeout=2)
    with pytest.raises(RuntimeError, match='appliance-api'):
        supervisor.start(check=True)


def test_critical_core_exit_stops_the_service(stack):
    supervisor, _, _ = stack()
    supervisor.start()
    supervisor.kill('native-auth')
    with pytest.raises(supervision.CriticalExit, match='native-auth'):
        until(supervisor, lambda: False, timeout=5)


def test_critical_core_must_become_ready(stack):
    dead = supervision.Component(name='native-auth', critical=True, env=None,
                                 command=[sys.executable, '-c', 'raise SystemExit(1)'],
                                 health=(f'http://127.0.0.1:{free_port()}/health', {}))
    supervisor = supervision.Supervisor([dead], cwd=Path.cwd(), log_dir=Path.cwd(), ready_timeout=2)
    try:
        with pytest.raises(supervision.CriticalExit):
            supervisor.start()
    finally:
        supervisor.stop()


def test_restart_backoff_is_bounded_and_resets_after_stable_running():
    delays = [supervision.restart_delay(n, initial=1, maximum=60) for n in range(1, 10)]
    assert delays == [1, 2, 4, 8, 16, 32, 60, 60, 60]
    assert supervision.restart_delay(0, initial=1, maximum=60) == 0


def test_restart_is_delayed_by_backoff(stack):
    flapping = supervision.Component(name='portal', critical=False, env=None,
                                     command=[sys.executable, '-c', 'raise SystemExit(1)'])
    supervisor, _, _ = stack([flapping], backoff_initial=.4, backoff_max=.4)
    supervisor.start()
    until(supervisor, lambda: supervisor.failures('portal') >= 1)
    first = supervisor.failures('portal')
    time.sleep(.1)
    supervisor.poll()
    assert supervisor.failures('portal') == first  # not restarted inside the backoff window
    until(supervisor, lambda: supervisor.failures('portal') > first)
