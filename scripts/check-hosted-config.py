"""Read-only provider checks; never print credentials or provider response bodies."""
import json
from email.utils import parseaddr
from pathlib import Path

import httpx
from dotenv import dotenv_values

path = Path(__file__).resolve().parents[1] / '.local/hosted/server.env'
config = dotenv_values(path)
required = ('STRIPE_SECRET_KEY', 'STRIPE_WEBHOOK_SECRET', 'STRIPE_RDP_PRICE_ID', 'RESEND_API_KEY')
result = {'configured': {key: bool(config.get(key)) for key in required}}
key = config.get('STRIPE_SECRET_KEY') or ''
result['stripe_test_mode'] = key.startswith(('sk_test_', 'rk_test_'))
result['stripe_live_mode'] = key.startswith(('sk_live_', 'rk_live_'))
result['stripe_publishable_key_supplied'] = key.startswith('pk_')
try:
    with httpx.Client(timeout=20, trust_env=False) as client:
        if result['stripe_test_mode'] or result['stripe_live_mode']:
            response = client.get('https://api.stripe.com/v1/account',
                                  auth=(key, ''))
            result['stripe_account_status'] = response.status_code
            price = config.get('STRIPE_RDP_PRICE_ID') or ''
            if price.startswith('price_') and price.replace('_', '').isalnum():
                response = client.get('https://api.stripe.com/v1/prices/' + price,
                                      auth=(key, ''))
                result['stripe_price_status'] = response.status_code
                if response.is_success:
                    data = response.json()
                    result['price'] = {name: data.get(name) for name in
                                       ('active', 'livemode', 'currency', 'unit_amount', 'type')}
                    result['price']['interval'] = (data.get('recurring') or {}).get('interval')
            response = client.get('https://api.stripe.com/v1/webhook_endpoints',
                                  params={'limit': 100}, auth=(key, ''))
            result['stripe_webhooks_status'] = response.status_code
            if response.is_success:
                result['planned_endpoint'] = [
                    {'status': item['status'], 'enabled_events': item['enabled_events']}
                    for item in response.json().get('data', [])
                    if item.get('url') == 'https://license.blissitek.ca/v1/webhooks/stripe']
        if config.get('RESEND_API_KEY'):
            response = client.get('https://api.resend.com/domains',
                headers={'Authorization': 'Bearer ' + config['RESEND_API_KEY']})
            result['resend_domains_status'] = response.status_code
            if response.status_code == 401:
                result['resend_sending_only_key'] = response.json().get('name') == 'restricted_api_key'
            if response.is_success:
                domain = parseaddr(config.get('MAIL_FROM') or '')[1].rpartition('@')[2]
                result['sender_domain'] = domain
                result['sender_verification'] = [item.get('status')
                    for item in response.json().get('data', []) if item.get('name') == domain]
except httpx.HTTPError as exc:
    result['connection_error'] = type(exc).__name__
print(json.dumps(result, indent=2))
