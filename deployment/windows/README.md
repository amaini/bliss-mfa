# Windows release inputs

`build-inputs.json` pins every third-party file in the customer download by URL,
SHA-256 and size. `appliance-requirements.lock` pins every embedded Python wheel
by hash. `scripts/fetch-build-inputs.py` downloads only verified content, verifies
archive members after extraction, exports the patched multiOTP engine from its
pinned commit, and lays the files out for `scripts/build-vm-package.py`.

| Input | Version | Publisher signature |
|---|---|---|
| Embedded CPython | 3.12.10 (`python-3.12.10-embed-amd64.zip`) | python.org release |
| Node.js runtime | 24.19.0 (`win-x64/node.exe`) | OpenJS Foundation (Authenticode) |
| PHP runtime | 8.3.35 NTS VS16 x64 | windows.php.net release |
| Windows service wrapper | WinSW 2.12.0 x64 | unsigned upstream; hash-pinned again at install |
| Visual C++ runtime | content-addressed Microsoft URL | Microsoft Corporation (checked at install) |
| Credential Provider | stock multiOTP Credential Provider 5.10.2.2 MSI | SysCo (checked at install) |
| multiOTP engine | `engine/windows-prototype` @ `85425f2` | this repository |

```sh
python scripts/fetch-build-inputs.py --output ../release-build/fetched --cache ../release-build/cache
```

To change a pin, download the new file from its publisher, verify its signature or
published checksum, update URL, SHA-256 and size together, and record why. Regenerate
the wheel lock with:

```sh
uv pip compile deployment/windows/appliance-requirements.in --python-platform x86_64-pc-windows-msvc \
  --python-version 3.12 --generate-hashes --only-binary :all: --no-header -o deployment/windows/appliance-requirements.lock
```
