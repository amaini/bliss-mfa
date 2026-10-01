# GitHub source checkout

The application, portal, website page, and deployment scripts are on `main` at
https://github.com/amaini/bliss-mfa. The patched multiOTP engine, including its
upstream license files and contribution libraries, is on the separate
`engine/windows-prototype` branch of that repository.

Clone the two branches side by side for scripts that expect the engine sibling:

```sh
git clone --branch main https://github.com/amaini/bliss-mfa.git bliss-mfa
git clone --single-branch --branch engine/windows-prototype https://github.com/amaini/bliss-mfa.git multiotp-engine
```

`website/windows-mfa/PUBLISHING.md` describes website publishing.
`deployment/hosted/PORTAINER.md` describes the selected backend deployment.
`docs/development-status.md` records completed validation and remaining acceptance.

Private `.local` files, credentials, signing keys, databases, VM enrollment data,
downloaded runtimes, and built installer archives are excluded from Git. They
must be provisioned separately. Package scripts describe the local build inputs;
a source clone alone does not contain the ready-built Windows installer.
