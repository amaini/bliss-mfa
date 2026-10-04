from fastapi import FastAPI
from fastapi.testclient import TestClient

from license_server.updates import mount_update_feed


def test_public_feed_and_traversal(tmp_path):
    public = tmp_path / 'updates'
    public.mkdir()
    (public / 'stable.json').write_text('{"payload":"signed-manifest"}')
    (public / 'release.zip').write_bytes(b'zip')
    (tmp_path / 'secret.txt').write_text('private')
    app = FastAPI()
    mount_update_feed(app, str(public))
    client = TestClient(app)
    assert client.get('/updates/stable.json').json() == {'payload': 'signed-manifest'}
    assert client.get('/updates/release.zip').content == b'zip'
    assert client.get('/updates/%2e%2e/secret.txt').status_code == 404
    assert client.get('/updates/').status_code == 404


def test_feed_disabled_by_default():
    app = FastAPI()
    mount_update_feed(app, None)
    assert TestClient(app).get('/updates/stable.json').status_code == 404
