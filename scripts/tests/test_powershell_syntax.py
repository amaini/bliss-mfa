"""Every shipped PowerShell script must parse under Windows PowerShell 5.1."""
import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS = sorted((Path(__file__).parents[1]).glob('*.ps1'))
pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell parser')
PARSE = ('$errors=$null; [void][System.Management.Automation.Language.Parser]::ParseFile($env:BLISS_SCRIPT,'
         '[ref]$null,[ref]$errors); if ($errors) { $errors | ForEach-Object { $_.Message }; exit 1 }')


@pytest.mark.parametrize('script', SCRIPTS, ids=lambda p: p.name)
def test_script_parses(script):
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', PARSE], capture_output=True, text=True,
                            env={**os.environ, 'BLISS_SCRIPT': str(script)})
    assert result.returncode == 0, result.stdout + result.stderr


def test_reinstall_inspects_identity_before_changing_any_file():
    text = (Path(__file__).parents[1] / 'Install-BlissEngine.ps1').read_text()
    assert text.index('--inspect-retained') < text.index('Merge-ReinstallFiles.ps1')
    assert "Test-Manifest $staging" in text
    assert text.index('Test-Manifest $staging') < text.index('Merge-ReinstallFiles.ps1')
