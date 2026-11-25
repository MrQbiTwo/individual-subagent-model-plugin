"""Branding contracts for the "Individual Subagent Model" display name.

The settled ruling keeps the technical ``Plugin.define`` server id while every
user-facing string uses the display name. A dedicated static check centralises
those rules; this module runs it and pins the surviving host identity id.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

DISPLAY = "Individual Subagent Model"
SERVER_ID = "individual-subagent-model-plugin"

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK = REPO_ROOT / "scripts" / "ci" / "check_branding.py"

REQUIRED_CHECKS = (
    "readme_display_name",
    "contributing_display_name",
    "server_plugin_id_unchanged",
    "no_effort_in_user_facing_copy",
)


def _run_check() -> dict:
    assert CHECK.is_file(), f"branding static check is missing: {CHECK}"
    result = subprocess.run(
        [sys.executable, str(CHECK)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"branding static check failed:\n{result.stdout}\n{result.stderr}"
    )
    return json.loads(result.stdout)


def test_branding_static_check_passes() -> None:
    report = _run_check()
    assert report["ok"] is True, report


def test_branding_static_check_covers_all_contracts() -> None:
    report = _run_check()
    checks = report["checks"]
    for name in REQUIRED_CHECKS:
        assert name in checks, f"branding check {name!r} is missing: {checks}"


def test_server_plugin_id_remains_unchanged() -> None:
    assert f'id: "{SERVER_ID}"' in _read("opencode/src/adapters/opencode_cli/server.ts")


def test_display_name_is_used_in_user_facing_copy() -> None:
    assert DISPLAY in _read("README.md")
    assert DISPLAY in _read("CONTRIBUTING.md")


def _read(relative: str) -> str:
    path = REPO_ROOT / relative
    assert path.is_file(), f"{relative} is missing"
    return path.read_text(encoding="utf-8")
