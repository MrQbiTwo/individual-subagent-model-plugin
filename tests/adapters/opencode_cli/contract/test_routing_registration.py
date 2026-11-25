"""CLI routing adapter registers the host hooks without changing decisions."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
PROBE = REPO_ROOT / "opencode" / "tools" / "adapters" / "cli" / "routing_registration_probe.mjs"


def test_routing_registration_probe() -> None:
    result = subprocess.run(
        ["node", str(PROBE)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, f"routing probe failed:\n{result.stdout}\n{result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["ok"] is True, payload
    assert payload["registrations"] == 5
