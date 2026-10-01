import httpx
import pytest
from fastapi import HTTPException

from license_server import customer_auth
from license_server.config import get_settings


@pytest.fixture
def mail_settings(monkeypatch):
    monkeypatch.setenv('RESEND_API_KEY', 're_private_test_key')
    monkeypatch.setenv('CUSTOMER_PORTAL_URL', 'https://license.blissitek.ca')
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_resend_delivery_and_idempotency(mail_settings, monkeypatch):
    def post(url, **kwargs):
        assert url == 'https://api.resend.com/emails'
        assert kwargs['headers']['Authorization'] == 'Bearer re_private_test_key'
        assert 'private-test-token' not in kwargs['headers']['Idempotency-Key']
        assert kwargs['json']['to'] == ['owner@example.com']
        assert '#verify=private-test-token' in kwargs['json']['text']
        return httpx.Response(200, json={'id': 'test-message'}, request=httpx.Request('POST', url))
    monkeypatch.setattr(customer_auth.httpx, 'post', post)
    customer_auth.send_account_mail('owner@example.com', 'private-test-token', 'verify')


@pytest.mark.parametrize('status,body', [(429, {'message': 'private-test-token'}),
                                       (500, {'error': 'private-test-token'}), (200, {})])
def test_delivery_failure_does_not_expose_secrets(mail_settings, monkeypatch, status, body):
    monkeypatch.setattr(customer_auth.httpx, 'post', lambda url, **kw:
        httpx.Response(status, json=body, request=httpx.Request('POST', url)))
    with pytest.raises(HTTPException) as error:
        customer_auth.send_account_mail('owner@example.com', 'private-test-token', 'reset')
    assert error.value.status_code == 503
    assert 'private' not in error.value.detail
