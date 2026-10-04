# Windows subscription pilot

The first commercial milestone is a small Windows paid pilot. Version 0.1.2 is
a release candidate until the installation and payment acceptance below is
recorded against the exact downloadable ZIP. Passing source tests does not
establish that the deployed backend or customer computer runs this version.

## Customer journey

1. Register in the hosted customer portal and verify the email address.
2. Start the one-seat, 14-day trial or subscribe for the needed protected-user seats.
3. Download the verified Windows installer and generate an activation code.
4. Install as a Windows administrator with independent console recovery available.
5. Create the private appliance owner and activate the license.
6. Add an existing Windows account, scan its QR code, and verify a fresh OTP.
7. Enable RDP protection after the installed native client verifies a fresh OTP.
8. Test sign-in and rejection paths before using the appliance for office access.
9. Use the hosted billing page to manage the subscription and local Start menu
   shortcut for signed application updates.

Licensing counts distinct protected RDP users, not concurrent sessions. Trial
conversion preserves the appliance identity and enrollment. Expired billing
restricts commercial management without automatically disabling established
authentication. Uninstalling protection does not cancel billing; customers use
the billing portal to cancel. Passwords, MFA seeds and authentication traffic
stay in the customer environment.

After a completed cancellation, customers can subscribe again and retain their
existing appliance. Active or overdue subscriptions are managed through billing
to avoid duplicate purchases. Use **Refresh subscription status** if a billing
change is not yet reflected. Administrator-revoked licenses require support;
payment does not reverse that revocation.

## Acceptance before taking pilot customers

Record exact source commit, artifact SHA256, Windows edition/build, provider
version, recovery route, and backend deployment version with every result.

| Acceptance | Required evidence |
|---|---|
| Clean installation | Fresh disposable target, correct installer signature checks, private data ACL, service readiness, shortcuts and uninstaller |
| Trial onboarding | Real registration email, one-time trial, installer download, local owner, activation, enrollment and seat limit |
| Paid onboarding | Stripe delivery linked to the real purchase, active owned license, matching download hash and installed activation |
| Windows authentication | Fresh OTP succeeds; wrong password, incorrect/empty OTP and replay fail; lock/unlock, reconnect and reboot behave as intended |
| Billing changes | Test-mode renewal, failed payment, seat changes and cancellation reconcile; repeated/out-of-order webhooks do not duplicate licenses |
| Application update | Pinned public key, signed manifest, release hash, successful actual-release upgrade with state preservation |
| Failed update | Failed readiness restores application and database, leaving independent recovery access |
| Backup recovery | Encrypted full snapshot restored separately, readiness verified, passphrase retained separately |
| Supported deployment | Tested Windows edition/build receiving vendor security updates; broader editions are outside the initial pilot |

Use isolated identities and Stripe test mode for failure scenarios. A live
purchase has already been reported historically; do not create another charge
solely to repeat tests. Confirm its actual webhook and activation evidence.

## Release preparation

The update signing key is separate from licensing. Generate it with
`scripts/generate-update-keys.py --directory PRIVATE_SIGNING_DIRECTORY` on the
designated signing computer. The tool creates a restricted directory before
writing private bytes and refuses to replace an existing or partial key pair.
Keep a secure offline recovery copy. Customer archives contain only public keys.

`build-vm-package.py` accepts `--work-root`, `--input-directory`,
`--license-public-key`, `--update-public-key` and `--output` so the release can be
built from an isolated checkout using verified local runtimes. Use a new output
path for each build: the script refuses to overwrite an existing ZIP. Supply the
fresh portal build and an audited Node runtime. Its public keys must be distinct
Ed25519 keys; missing prerequisites fail before archive creation.

Build the customer wrapper with `build-client-release.py`. Build and sign the
application update with `publish-client-update.py`, then verify its signature,
archive paths, manifest and hashes locally. Test the exact release on the VM
before publishing. Follow `deployment/hosted/INSTALLER.md` for the paid installer
mount/checksum and `deployment/hosted/UPDATES.md` for the public-only update feed.

Publishing source code does not update customers. Existing clients need the
pinned public key and updater integration provisioned once. Never substitute a
different signing key or bypass installer integrity checks to repair deployment.

## Pilot operations

For each pilot customer retain the customer/license reference, seat count,
approved Windows build and installed release; exclude MFA secrets and passwords.
Provide the setup, recovery, billing-cancellation and update instructions with
the download. Agree the support contact, support hours and pilot terms before
accepting customers. Check service health, webhook failures and backups and
record failures as launch blockers until resolved. A public health endpoint
alone does not prove email delivery, valid downloads or working Windows MFA.
