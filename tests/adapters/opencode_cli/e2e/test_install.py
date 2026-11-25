"""Install and load smoke tests executed on every runner.

The package now ships only the server entrypoint and the RPC compatibility
entrypoint; there is no TUI or GUI bundle to assert.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import skip_test

# npm ci / npm run build share node_modules and dist, so --dist=loadgroup
# pins all three tests to one worker, sequentially.
pytestmark = [pytest.mark.e2e, pytest.mark.xdist_group("serial_npm")]

REPO_ROOT = Path(__file__).resolve().parents[4]
PACKAGE_DIR = REPO_ROOT / "opencode"


def _package_ready() -> str:
    """Return the npm executable path, or skip when prerequisites are absent."""
    if os.environ.get("OPENCODE_TEST_SKIP_INSTALL") == "1":
        skip_test("OPENCODE_TEST_SKIP_INSTALL=1 (install/build already done by CI)")
    if not (PACKAGE_DIR / "package.json").is_file():
        skip_test("opencode/package.json is not present yet")
    npm = shutil.which("npm")
    if npm is None:
        skip_test("npm is not on PATH")
    return npm


def test_npm_ci_succeeds() -> None:
    npm = _package_ready()
    result = subprocess.run(
        [npm, "ci", "--prefix", "opencode"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, f"npm ci failed:\n{combined}"


def test_server_entry_resolves() -> None:
    npm = _package_ready()
    build = subprocess.run(
        [npm, "run", "build", "--prefix", "opencode"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    assert build.returncode == 0, f"npm run build failed:\n{build.stdout}\n{build.stderr}"
    dist = PACKAGE_DIR / "dist"
    assert (dist / "index.js").is_file(), "server entrypoint was not emitted"
    assert (dist / "rpc.js").is_file(), "RPC compatibility entrypoint was not emitted"
    assert not (dist / "tui.js").exists(), "removed TUI entrypoint was rebuilt"
    assert not (dist / "gui-experimental.cjs").exists(), "removed GUI bundle was rebuilt"


def test_load_on_arm_runner() -> None:
    """ARM runners must additionally prove the built server entry can be imported."""
    if platform.machine().lower() not in ("arm64", "aarch64"):
        skip_test("ARM-only import smoke check")
    _package_ready()
    assert (PACKAGE_DIR / "dist" / "index.js").is_file(), "server entrypoint missing on ARM"
    result = subprocess.run(
        ["node", "-e", "import('./dist/index.js')"],
        cwd=PACKAGE_DIR,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, f"server entry import failed on ARM:\n{result.stderr}"
