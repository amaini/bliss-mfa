# Contabo / CyberPanel / LXD / Portainer handoff

Target: Ubuntu 24.04 VPS with CyberPanel and an existing Docker endpoint inside
an LXD container. This stack is for Docker Standalone, not Swarm. It is prepared,
not deployed. The agent deploying it needs shell access to that Docker endpoint
and CyberPanel/DNS access. Website publishing alone does not run the backend.

## Prepare inside the Docker-host LXD container

Copy `apps/license-server` from the handoff archive to `/opt/bliss-mfa/source`.
Build on the same Docker endpoint managed by Portainer:

```sh
cd /opt/bliss-mfa/source
docker build -t bliss-license:prototype .
```

Provision these files separately through a private transfer, outside WordPress's
web root. Paths refer to the Docker endpoint's filesystem, not the VPS parent or
the Portainer container:

- `/opt/bliss-mfa/private/license-private.pem`: existing Ed25519 signing key.
- `/opt/bliss-mfa/releases/windows.zip`: tested customer release.

Protect the private directory and key (owner root; directory 0700, key 0600).
Keep the same key across upgrades; installed clients contain its public key.
Do not generate a replacement key silently. Recompute the release SHA-256 and
set `APPLIANCE_RELEASE_SHA256` to that digest. Back up the database volume and
signing key before upgrades; restore them together and preserve this image.

## Deploy with Portainer

Create a stack named `bliss-license` on the Docker Standalone endpoint and paste
`portainer-stack.yaml`. Add private settings through the environment form or its
private `.env` import: use the existing `server.env` listed in `README.md`.
Set `BLISS_BIND_IP` to the LXD container's private address reachable by CyberPanel.
If Docker and CyberPanel share a network namespace, use 127.0.0.1 instead.
Do not use the public IP or 0.0.0.0 for this bind.

Portainer exposes its supplied variables through `stack.env`. This contains
credentials: restrict Portainer access and do not export the populated stack.
The image must already exist on that endpoint; it is not in a public registry.
This stack has no Caddy and takes neither port 80 nor port 443.

Restrict port 18080 to the CyberPanel host with the endpoint/LXD firewall. Check
from the CyberPanel host that `http://LXD_PRIVATE_IP:18080/health` responds.
Check that the container is healthy and its migration completed. Confirm the
database volume persists through a stack restart.

## CyberPanel HTTPS proxy

Create the `license.blissitek.ca` website/vhost and a valid TLS certificate.
Point its DNS record to the VPS. On that vhost, configure an OpenLiteSpeed
Web Server external application targeting `LXD_PRIVATE_IP:18080`, and a root
proxy context `/` using that external application. Preserve the public Host
header; exclude account/API responses from page caching. Do not overwrite the
existing blissitek.ca WordPress vhost. Test the exact settings against the
installed CyberPanel/OpenLiteSpeed version and retain a configuration backup.

Do not expose the container's HTTP port publicly. Visit
`https://license.blissitek.ca/health` and `/customer` through the public proxy.
Confirm secure cookies, email links, billing returns and downloads all use the
public HTTPS origin. The backend owns the complete subdomain, including `/v1`.

## Acceptance before opening purchases

Follow the Stripe event list and customer journey in `README.md`. Configure the
live webhook at `https://license.blissitek.ca/v1/webhooks/stripe` and privately
replace `STRIPE_WEBHOOK_SECRET` with that endpoint's signing secret. Restart to
load it. Verify registration/email, signed webhook delivery, a deliberate live
purchase, active license/download, activation, clean Windows installation and
actual RDP sign-in/rejection/recovery. A health endpoint alone is insufficient.
Then enable the links described in `website/windows-mfa/PUBLISHING.md`.

References: [Portainer stack environment variables](https://docs.portainer.io/sts/user/docker/stacks/add)
and [OpenLiteSpeed reverse proxy configuration](https://docs.openlitespeed.org/config/reverseproxy/).
