# Fix paid installer download integrity failure

An active one-seat paid account was confirmed in the supplied purchase screenshot.
The portal displays “Installer integrity check failed”; that specifically means
the mounted ZIP's SHA-256 differs from APPLIANCE_RELEASE_SHA256. Do not disable
the hash check, grant a second license, or ask the customer to pay again.

Verified release:
https://github.com/amaini/bliss-mfa/releases/tag/v0.1.0-windows-prototype

Outer customer ZIP SHA-256:
`8f68396a7d11ec3af353c44533b1db78005a4baeb72a4beac4621e29e279ce38`

This is the outer ZIP containing Setup-BlissMFA.cmd, not the inner appliance ZIP.

On the Docker-host LXD container, download into a temporary file and verify before
replacing the deployed release:

```sh
set -eu
mkdir -p /opt/bliss-mfa/releases
curl --fail --location --output /opt/bliss-mfa/releases/windows.zip.new \
  https://github.com/amaini/bliss-mfa/releases/download/v0.1.0-windows-prototype/bliss-mfa-windows-prototype.zip
echo '8f68396a7d11ec3af353c44533b1db78005a4baeb72a4beac4621e29e279ce38  /opt/bliss-mfa/releases/windows.zip.new' | sha256sum --check
mv /opt/bliss-mfa/releases/windows.zip.new /opt/bliss-mfa/releases/windows.zip
```

Set Portainer's private stack environment to:

```text
APPLIANCE_RELEASE_SHA256=8f68396a7d11ec3af353c44533b1db78005a4baeb72a4beac4621e29e279ce38
APPLIANCE_RELEASE_FILE=/run/bliss-release/windows.zip
```

Keep the read-only mount from `/opt/bliss-mfa/releases/windows.zip` to that
container path. Recreate the license-server container after replacing the file
and loading settings. File bind mounts can retain the previous inode after a
host-side rename; restarting only the application may still serve the old file.
Preserve PostgreSQL volumes, password files, and the existing signing key.

Inside the running backend, check with this single command (prints only release
configuration, not any Stripe/Resend/other secrets):

```sh
python -c "from license_server.customer_routes import release_file; p=release_file(); print('Verified installer available:', bool(p))"
```

Expected: `Verified installer available: True`. Refresh the paid client portal,
download the ZIP, check its hash, extract, and run Setup-BlissMFA.cmd on a clean
disposable Windows target. This is still a prototype; clean-install and further
interactive RDP acceptance remain required. Do not reuse the already installed
test VM as proof of a clean installation.
