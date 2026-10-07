"""Fixed-script PHP-CGI gateway for native XML authentication.

No request-controlled filenames, CGI environment, or subprocess arguments.
One engine operation at a time preserves the prototype's file-backed state.
"""
import asyncio
import os
import subprocess
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import Response

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
gate = asyncio.Semaphore(1)
LIMIT = 65536


def execute(body: bytes, health: bool = False) -> Response:
    env = os.environ.copy()
    script = str(Path(env['BLISS_NATIVE_ROUTER']).resolve())
    env.update(REDIRECT_STATUS='200', SCRIPT_FILENAME=script, SCRIPT_NAME='/router.php',
               REQUEST_URI='/health' if health else '/auth',
               REQUEST_METHOD='GET' if health else 'POST',
               CONTENT_TYPE='application/x-www-form-urlencoded', CONTENT_LENGTH=str(len(body)),
               QUERY_STRING='', SERVER_PROTOCOL='HTTP/1.1', SERVER_NAME='localhost',
               SERVER_PORT='18443', REMOTE_ADDR='127.0.0.1')
    command = [env['BLISS_PHP_CGI']]
    try:
        result = subprocess.run(command, input=body, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, env=env, timeout=15, check=False,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        headers, payload = result.stdout.split(b'\r\n\r\n', 1)
        if result.returncode != 0 or len(payload) > 262144:
            raise ValueError('Invalid CGI response')
        status = 200
        for line in headers.decode('ascii').splitlines():
            if line.lower().startswith('status:'):
                status = int(line.split(':', 1)[1].strip().split()[0])
        if status not in {200, 400, 404, 413, 503}:
            raise ValueError('Unexpected status')
        # Never forward PHP diagnostic output on failure.
        if status != 200:
            payload = b''
        elif health and payload != b'{"status":"ok"}':
            raise ValueError('Invalid health response')
        elif not health and b'<multiOTP' not in payload:
            raise ValueError('Invalid XML response')
        return Response(payload, status_code=status,
                        media_type='application/json' if health else 'application/xml',
                        headers={'Cache-Control': 'no-store', 'Connection': 'close'})
    except (OSError, subprocess.TimeoutExpired, ValueError, UnicodeError):
        return Response(status_code=503, headers={'Cache-Control': 'no-store', 'Connection': 'close'})


@app.get('/health')
async def health():
    async with gate:
        return await asyncio.to_thread(execute, b'', True)


@app.post('/auth')
async def authenticate(request: Request):
    if request.headers.get('content-type', '').split(';')[0].lower() != 'application/x-www-form-urlencoded':
        return Response(status_code=415)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > LIMIT:
            return Response(status_code=413)
    if not body:
        return Response(status_code=400)
    try:
        await asyncio.wait_for(gate.acquire(), timeout=2)
    except TimeoutError:
        return Response(status_code=503)
    try:
        return await asyncio.to_thread(execute, bytes(body))
    finally:
        gate.release()
