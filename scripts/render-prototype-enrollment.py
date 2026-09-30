"""Render a private, self-contained operator enrollment page on the disposable VM."""
import base64
import html
import json
from pathlib import Path

import pyotp
import qrcode
from qrcode.image.svg import SvgPathImage

root = Path('C:/BlissMFA')
data = json.loads((root / 'prototype-test-account.json').read_text(encoding='utf-8-sig'))
otp = pyotp.parse_uri(data['provisioning_uri'])
qr = qrcode.make(data['provisioning_uri'], image_factory=SvgPathImage)
image = base64.b64encode(qr.to_string()).decode('ascii')
account = 'WIN-10VM-ASUS\\' + data['username']
page = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer"><title>Bliss MFA · Prototype enrollment</title>
<style>body{{margin:0;background:#eef2f8;color:#142039;font:17px/1.55 system-ui,sans-serif}}main{{max-width:760px;margin:48px auto;padding:40px;background:white;border-radius:20px;box-shadow:0 12px 40px #14203912}}h1{{font-size:32px;margin:12px 0}}h2{{font-size:21px;margin-top:28px}}.tag{{color:#3d5dc4;font-size:14px;font-weight:700}}code{{word-break:break-all;background:#eef2f8;padding:4px 8px;border-radius:5px}}img{{width:280px;max-width:100%;display:block}}details{{margin:12px 0}}li{{margin:10px 0}}a{{color:#3158c9}}@media(max-width:800px){{main{{margin:16px;padding:24px}}}}</style>
<main><div class="tag">BLISS MFA · DISPOSABLE VM</div><h1>Enroll your test account</h1>
<p>The engine is installed. Use this account to verify Windows Remote Desktop MFA.</p>
<h2>1. Add your authenticator</h2><p>Scan this QR code using your authenticator app.</p>
<img alt="Authenticator enrollment QR code" src="data:image/svg+xml;base64,{image}">
<details><summary>Enter the key manually</summary><p>Account: <code>{html.escape(data['username'])}</code></p><p>Key: <code>{html.escape(otp.secret)}</code></p><p>Time based · 6 digits · 30 seconds</p></details>
<h2>2. Connect using Remote Desktop</h2><p>Address: <code>100.83.112.5</code></p><p>Windows account: <code>{html.escape(account)}</code></p>
<details><summary>Show the test Windows password</summary><p><code>{html.escape(data['windows_password'])}</code></p></details>
<p>Choose the Bliss MFA / multiOTP sign-in tile and enter a fresh authenticator code when prompted.</p>
<h2>3. Check enforcement</h2><ol><li>A correct Windows password and fresh OTP should sign in.</li><li>A correct password with an incorrect or empty OTP should be denied.</li><li>A wrong Windows password with a fresh OTP should be denied.</li><li>After a successful sign-in, sign out and try the same OTP before it changes. Replay should be denied.</li></ol>
<p>The existing <code>WIN-10VM-ASUS\\Abhishek</code> administrator account remains the recovery exception. Local console sign-in keeps its normal password flow.</p>
<p>This is the engine deployment. Customer purchase and onboarding remain a later stage.</p></main></html>'''
(root / 'Prototype-Enrollment.html').write_text(page, encoding='utf-8')
print('Private enrollment page: C:\\BlissMFA\\Prototype-Enrollment.html')
