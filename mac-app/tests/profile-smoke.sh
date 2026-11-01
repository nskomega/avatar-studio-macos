#!/bin/zsh
set -eu
cd "$(dirname "$0")/../.."
# Extract UI definitions, excluding the interactive application entry point.
python3 - <<'PYTEST'
from pathlib import Path
source=Path('mac-app/Sources/main.swift').read_text().split('let app=NSApplication.shared')[0]
checks=Path('mac-app/tests/profile-checks.swift').read_text()
Path('mac-app/jobs/profile-test.swift').write_text(source+checks)
PYTEST
xcrun swiftc -framework AppKit mac-app/jobs/profile-test.swift -o mac-app/jobs/profile-test
mac-app/jobs/profile-test
