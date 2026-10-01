import subprocess

import pytest
from fastapi.testclient import TestClient

from adapter import native


@pytest.fixture
def client(monkeypatch, tmp_path):
    for key, value in {'BLISS_NATIVE_ROUTER': str(tmp_path / 'router.php'),
                       'BLISS_PHP_CGI': 'php-cgi.exe'}.items():
        monkeypatch.setenv(key, value)
    return TestClient(native.app)


def test_routes_and_request_limits(client, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid request invoked engine')
    monkeypatch.setattr(native.subprocess, 'run', forbidden)
    assert client.get('/admin').status_code == 404
    assert client.get('/auth').status_code == 405
    assert client.post('/auth', content=b'x').status_code == 415
    assert client.post('/auth', content=b'x' * 65537,
                       headers={'content-type': 'application/x-www-form-urlencoded'}).status_code == 413


@pytest.mark.parametrize('output,exitcode,expected', [
    (b'Content-Type: application/json\r\n\r\n{"status":"ok"}', 0, 200),
    (b'Content-Type: text/html\r\n\r\nPrivate PHP error', 0, 503),
    (b'Status: 503 Unavailable\r\n\r\nPrivate PHP error', 0, 503),
    (b'broken CGI headers', 0, 503),
    (b'Content-Type: application/json\r\n\r\n{"status":"ok"}', 1, 503),
])
def test_failure_output_is_not_disclosed(client, monkeypatch, output, exitcode, expected):
    monkeypatch.setattr(native.subprocess, 'run', lambda *a, **kw:
                        subprocess.CompletedProcess(a, exitcode, stdout=output))
    response = client.get('/health')
    assert response.status_code == expected
    assert b'Private' not in response.content


def test_timeout_fails_closed(client, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('private command', 15)
    monkeypatch.setattr(native.subprocess, 'run', timeout)
    assert client.get('/health').status_code == 503


def test_fixed_router_and_no_request_environment(client, monkeypatch):
    def run(command, **kwargs):
        assert command == ['php-cgi.exe']
        assert kwargs['env']['SCRIPT_FILENAME'].endswith('router.php')
        assert kwargs['env']['REQUEST_URI'] == '/auth'
        assert 'HTTP_BLISS_ENGINE_SHARED_SECRET' not in kwargs['env']
        return subprocess.CompletedProcess(command, 0, stdout=b'Content-Type: application/xml\r\n\r\n<multiOTP/>')
    monkeypatch.setattr(native.subprocess, 'run', run)
    response = client.post('/auth', content=b'data=xml', headers={
        'content-type': 'application/x-www-form-urlencoded', 'bliss-engine-shared-secret': 'attacker'})
    assert response.status_code == 200
