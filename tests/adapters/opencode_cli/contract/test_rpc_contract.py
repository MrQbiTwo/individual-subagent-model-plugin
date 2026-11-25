"""Wire contract of the OpenCode CLI RPC adapter."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
PROBE = REPO_ROOT / "opencode" / "tools" / "adapters" / "cli" / "rpc_contract_probe.mjs"


def test_rpc_contract_probe() -> None:
    result = subprocess.run(
        ["node", str(PROBE)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, f"RPC contract probe failed:\n{result.stdout}\n{result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["ok"] is True, payload
    assert payload["namespace"] == "subagent-models"
    assert payload["methods"] == ["get_catalog", "get_policy", "set_policy"]
    assert payload["events"] == ["catalog_updated", "policy_updated"]
    assert payload["http_path"] == "/api/rpc/subagent-models/get_catalog"
