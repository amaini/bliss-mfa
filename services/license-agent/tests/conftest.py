"""Keep tests off the production state directory.

license_agent.main creates its LicenseState at import time from settings.state_dir, whose default
(/var/lib/bliss-mfa/license) is not writable on CI runners or developer machines.
"""
import os
import tempfile

os.environ.setdefault("STATE_DIR", tempfile.mkdtemp(prefix="bliss-license-agent-tests-"))
