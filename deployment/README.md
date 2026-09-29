# Deployment

Production deployment assets will live here after the Phase 0 architecture/security review.

Initial production intent:

- public portal/API behind a reverse proxy or Cloudflare Tunnel
- PostgreSQL and Redis on private container networks
- multiOTP management endpoint not publicly exposed
- strict network policy between API and multiOTP adapter
- separate secrets from repository/config templates
