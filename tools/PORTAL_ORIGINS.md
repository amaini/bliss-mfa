# Portal authentication origin regression

The login and bootstrap handlers reject foreign or opaque Origin values and
Sec-Fetch-Site: cross-site before reading or forwarding the request body. Native
requests with no Origin remain supported. This is a browser request-origin guard,
not a replacement for authentication or trusted reverse-proxy configuration.

After installing dependencies and building apps/appliance-portal, run:

```powershell
python tools/check_portal_origins.py --portal apps/appliance-portal --node node --output outputs/portal-origin-results.json
```

Python requires httpx. The check launches the built portal on loopback against a
loopback dummy backend, uses empty payloads, creates no accounts, and stops its
owned server afterward. Eighteen checks cover page access, anonymous management
redirects, and blocked/allowed request-origin cases for both auth endpoints and backend writes. The comparison uses the browser Host
authority so Next.js loopback hostname normalization does not reject legitimate
IP-address origins. Run behind a proxy that preserves the public Host and scheme.
