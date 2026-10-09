import httpx
import pytest
from fastapi.testclient import TestClient

from adapter import portal_proxy


@pytest.fixture
def proxy(monkeypatch):
    requests = []
    def upstream(request):
        requests.append(request)
        return httpx.Response(200, text='portal response', headers=[
            ('Content-Type', 'text/plain'), ('Set-Cookie', 'first=1; Secure; HttpOnly'),
            ('Set-Cookie', 'second=2; Secure; HttpOnly')])
    client_class = httpx.AsyncClient
    monkeypatch.setattr(portal_proxy.httpx, 'AsyncClient',
        lambda **kwargs: client_class(transport=httpx.MockTransport(upstream), **kwargs))
    return TestClient(portal_proxy.app, base_url='https://localhost:19443'), requests


def test_untrusted_host_and_origin_do_not_reach_portal(proxy):
    client, requests = proxy
    assert client.get('/setup', headers={'Host': 'attacker.example'}).status_code == 400
    assert client.post('/api/auth/bootstrap', headers={'Origin': 'https://attacker.example'}).status_code == 403
    assert requests == []


def test_oversized_request_does_not_reach_portal(proxy):
    client, requests = proxy
    assert client.post('/api/auth/login', content=b'x' * 65537).status_code == 413
    assert requests == []


def test_proxy_forwards_fixed_destination_session_and_secure_response(proxy):
    client, requests = proxy
    response = client.post('/api/auth/login?return=onboarding',
        headers={'Origin': 'https://localhost:19443', 'Cookie': 'session=private',
                 'X-Forwarded-Host': 'attacker.example', 'Content-Type': 'application/json'},
        content=b'{}')
    assert response.status_code == 200
    assert str(requests[0].url) == 'http://127.0.0.1:19043/api/auth/login?return=onboarding'
    assert requests[0].headers['cookie'] == 'session=private'
    assert requests[0].headers['x-forwarded-host'] == 'localhost:19443'
    assert requests[0].headers['x-forwarded-proto'] == 'https'
    assert len(response.headers.get_list('set-cookie')) == 2
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['referrer-policy'] == 'no-referrer'


def test_failed_upstream_hides_internal_details(monkeypatch):
    client_class = httpx.AsyncClient
    def unavailable(request):
        raise httpx.ConnectError('private internal details', request=request)
    monkeypatch.setattr(portal_proxy.httpx, 'AsyncClient', lambda **kwargs:
        client_class(transport=httpx.MockTransport(unavailable), **kwargs))
    response = TestClient(portal_proxy.app, base_url='https://localhost:19443').get('/setup')
    assert response.status_code == 503
    assert 'private' not in response.text


@pytest.mark.parametrize('path,upstream_cache,expected', [
    # Pages and RSC payloads must never be cached: after an upgrade the browser has to load the new portal.
    ('/windows-accounts', 's-maxage=31536000', 'no-store'),
    ('/', 's-maxage=31536000, stale-while-revalidate', 'no-store'),
    # Content-hashed build assets keep Next's immutable caching.
    ('/_next/static/chunks/729-abc.js', 'public, max-age=31536000, immutable', 'public, max-age=31536000, immutable'),
])
def test_pages_are_never_cached_but_hashed_assets_are(monkeypatch, path, upstream_cache, expected):
    def upstream(request):
        return httpx.Response(200, text='x', headers={'Cache-Control': upstream_cache})
    client_class = httpx.AsyncClient
    monkeypatch.setattr(portal_proxy.httpx, 'AsyncClient',
        lambda **kwargs: client_class(transport=httpx.MockTransport(upstream), **kwargs))
    client = TestClient(portal_proxy.app, base_url='https://localhost:19443')
    assert client.get(path).headers['cache-control'] == expected
