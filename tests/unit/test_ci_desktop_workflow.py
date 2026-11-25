"""Static contract for the headless Desktop checks wired into CI.

No PyYAML dependency: the workflow shape is asserted from its text so the
checks stay dependency-free and run on every platform. The job is a contract
gate only -- hosted runners have no Electron session and ``opencode app`` does
not exist as a CLI subcommand.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DISPLAY = "Individual Subagent Model"
RUNNERS = (
    "ubuntu-24.04",
    "ubuntu-24.04-arm",
    "windows-latest",
    "macos-latest",
    "windows-11-arm",
)
# Assembled at runtime so this audit file does not trip the zero-WSL policy.
FORBIDDEN = (
    "/" + "mnt" + "/",
    "wsl" + chr(46) + "exe",
    "wsl" + "path",
    "WSL" + chr(95) + "ENV",
    "WSL" + chr(95) + "DISTRO_NAME",
)
TOP_LEVEL_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*:")
JOB_KEY = re.compile(r"^  [A-Za-z_][A-Za-z0-9_-]*:\s*$")


def _workflow() -> str:
    assert CI.is_file(), f"{CI} is missing"
    return CI.read_text(encoding="utf-8")


def _job_block(text: str, job_id: str) -> str:
    lines = text.splitlines()
    heading = re.compile(rf"^  {re.escape(job_id)}:\s*$")
    for index, line in enumerate(lines):
        if heading.match(line):
            collected = [line]
            for following in lines[index + 1 :]:
                if JOB_KEY.match(following):
                    break
                collected.append(following)
            return "\n".join(collected)
    raise AssertionError(f"job {job_id!r} is missing from ci.yml")


def test_desktop_contract_job_exists() -> None:
    job = _job_block(_workflow(), "desktop_contract")
    assert "runs-on: ${{ matrix.os }}" in job
    assert "fail-fast: false" in job


def test_desktop_contract_matrix_has_all_five_labels() -> None:
    job = _job_block(_workflow(), "desktop_contract")
    for runner in RUNNERS:
        assert re.search(rf"^\s+- {re.escape(runner)}\s*$", job, re.MULTILINE), runner


def test_desktop_contract_checks_cli_version() -> None:
    job = _job_block(_workflow(), "desktop_contract")
    assert '"@opencode/cli@' in job
    assert "opencode --version" in job


def test_desktop_contract_checks_zero_commands() -> None:
    job = _job_block(_workflow(), "desktop_contract")
    assert "check_no_commands.py" in job, "zero-command guard is not invoked"
    assert "check_gui_bundle.py" not in job, "removed GUI bundle check is still invoked"
    assert "gui_command_registration_probe.mjs" not in job, "deleted GUI probe is still invoked"
    assert "./gui-experimental" not in job, "removed GUI export is still referenced"
    assert "tests/adapters/opencode_cli/e2e/test_config_file_control.py" in job, (
        "config-file control E2E is not invoked at its adapter path"
    )
    assert "scripts/run_tests.sh" in job
    assert "./scripts/run_tests.ps1" in job


def test_desktop_contract_has_least_privilege_and_failure_handling() -> None:
    job = _job_block(_workflow(), "desktop_contract")
    assert "contents: read" in job
    assert "issues: write" in job
    assert "if-no-files-found: ignore" in job


def test_promotion_and_auto_merge_need_desktop_contract() -> None:
    workflow = _workflow()
    for job_id in ("promote", "auto_merge"):
        job = _job_block(workflow, job_id)
        needs = re.search(r"^\s+needs:\s*\[(.*?)\]", job, re.MULTILINE)
        assert needs is not None, f"{job_id} has no needs list"
        assert "desktop_contract" in needs.group(1), f"{job_id} does not gate on Desktop"


def test_no_opencode_app_subcommand() -> None:
    assert "opencode app" not in _workflow(), "opencode app is not a CLI subcommand"


def test_workflow_security_baseline() -> None:
    workflow = _workflow()
    assert re.search(r"^permissions:\s*\{\}", workflow, re.MULTILINE) is not None
    uses = re.findall(r"^\s+uses:\s*(\S+)", workflow, re.MULTILINE)
    assert uses, "no pinned actions found"
    for action in uses:
        assert re.search(r"@[0-9a-f]{40}$", action), f"action is not SHA-pinned: {action}"
    for token in FORBIDDEN:
        assert token not in workflow, f"forbidden platform token in workflow: {token!r}"


def test_workflow_shape_has_required_top_level_keys() -> None:
    workflow = _workflow()
    keys = {
        match.group().rstrip(":")
        for line in workflow.splitlines()
        if (match := TOP_LEVEL_KEY.match(line))
    }
    assert {"name", "on", "concurrency", "permissions", "jobs"} <= keys
