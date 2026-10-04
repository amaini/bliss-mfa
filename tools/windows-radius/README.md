# Disposable Windows RADIUS lifecycle checks

This harness tests real loopback UDP PAP RADIUS with the patched multiOTP engine. It creates a disposable engine identity and isolated state, launches its own foreground RADIUS process on loopback, and stops that process after testing. It does not install services or credential providers or modify Windows accounts, RDP policy, firewall rules or registry settings.

## Run

Use an extracted Bliss-MFA-Test-Kit with its portable PHP runtime, patched engine and vendor RADIUS files. From this repository in normal Windows PowerShell:

```powershell
py -3.12 -m venv .local/radius-venv
& ./.local/radius-venv/Scripts/python.exe -m pip install -r ./tools/windows-radius/requirements.txt
& ./.local/radius-venv/Scripts/python.exe ./tools/windows-radius/run_radius_lifecycle.py --kit-root 'C:/BlissTest/Bliss-MFA-Test-Kit'
```

The kit root must contain `work/php-runtime`, `work/multiotp-engine`, and `work/multiotp-distribution/windows/radius`. Keep the full PHP runtime, including extensions and DLLs. Runtime binaries are not committed here. The vendor RADIUS distribution used for validation is multiOTP 5.10.2.2, with FreeRADIUS 2.2.6; the source ZIP URL and SHA-256 are recorded in each result JSON.

Allow several minutes for fresh OTP intervals. Expected result: **16/16**, process exit status zero, and all cleanup flags true in `outputs/radius-lifecycle-results.json` under the supplied kit root. Failed checks or incomplete cleanup return a nonzero status. Run sequentially against a given kit root because its result file is overwritten. Disposable labs contain generated secrets; keep them private and do not commit them.

## Path portability fix

The legacy RADIUS exec command cannot reliably launch the unquoted PHP and engine paths when extraction directories contain spaces. The harness maps two unused drive letters: one to its own disposable lab, and one to the existing runtime directory. All filesystem arguments passed to RADIUS exec are short and space-free, and both mappings are removed in cleanup. No partial runtime copies are used. Two free letters among R through Z are required.

Local validation passed 16/16 in the normal workspace and 16/16 from a separate extraction directory containing spaces. Both runs stopped their owned servers, removed the fake identity and removed both aliases. The original spare laptop still needs a rerun; these results do not establish Windows credential-provider or RDP MFA behavior.

If Python is forcibly terminated, cleanup cannot run. Inspect the specific lab and its owned process before recovery; stop only that test process and remove only its temporary mappings. Never change unrelated multiOTP state or services.
