"""Shipped text files must not contain bare carriage returns.

A stray CR inside a PowerShell comment ends the comment; the remainder then runs as a
command. It still parses, so only a byte-level check catches it (found on the test VM:
Install-WindowsIntegration.ps1 failed with "'elease-version.json' is not recognized").
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
SUFFIXES = {'.ps1', '.py', '.php', '.json', '.yml', '.yaml', '.toml', '.ts', '.tsx', '.js', '.cmd', '.md'}
TRACKED = [ROOT / name for name in subprocess.run(
    ['git', '-C', str(ROOT), 'ls-files', 'scripts', 'deployment', 'services', 'apps/appliance-api',
     'apps/license-server', 'apps/appliance-portal', 'tools'], capture_output=True, text=True, check=True).stdout.split()
    if Path(name).suffix.lower() in SUFFIXES]


@pytest.mark.parametrize('path', TRACKED, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_bare_carriage_return(path):
    data = path.read_bytes()
    match = re.search(rb'\r(?!\n)', data)
    assert match is None, f'bare CR at line {data[:match.start()].count(b"\n") + 1}'
