"""Loopback TLS entry point for the production-built local management portal."""
import os

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.api_route('/{path:path}', methods=['GET', 'POST', 'DELETE', 'HEAD'])
async def forward(request: Request, path: str):
    host = request.headers.get('host', '')
    port = os.environ.get('BLISS_PORTAL_TLS_PORT', '19443')
    if host not in {'localhost:' + port, '127.0.0.1:' + port}:
        return Response(status_code=400)
    if request.method not in {'GET', 'HEAD'}:
        origin = request.headers.get('origin')
        if origin and origin != 'https://' + host:
            return Response(status_code=403)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 65536:
            return Response(status_code=413)
    headers = {key: request.headers[key] for key in ('content-type', 'cookie') if key in request.headers}
    headers.update(host=host, **{'x-forwarded-host': host, 'x-forwarded-proto': 'https'})
    url = 'http://127.0.0.1:' + os.environ.get('BLISS_PORTAL_HTTP_PORT', '19043') + request.url.path
    if request.url.query:
        url += '?' + request.url.query
    try:
        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            upstream = await client.request(request.method, url, content=bytes(body), headers=headers)
        response = Response(upstream.content, status_code=upstream.status_code)
        for name in ('content-type', 'cache-control', 'location', 'vary', 'content-security-policy'):
            if name in upstream.headers:
                response.headers[name] = upstream.headers[name]
        for cookie in upstream.headers.get_list('set-cookie'):
            response.headers.append('set-cookie', cookie)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        # Only content-hashed build assets may be cached. Pages and RSC payloads are no-store, so a
        # browser always loads the portal that is installed now, not one from before an upgrade.
        response.headers['Cache-Control'] = (response.headers.get('cache-control', 'no-store')
                                             if path.startswith('_next/static/') else 'no-store')
        return response
    except httpx.HTTPError:
        return Response(status_code=503)
