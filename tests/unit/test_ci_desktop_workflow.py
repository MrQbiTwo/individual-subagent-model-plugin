"""Static contract for the headless Desktop checks and the release workflow.

No PyYAML dependency: the workflow shape is asserted from its text so the
checks stay dependency-free and run on every platform. The Desktop job is a
contract gate only -- hosted runners have no Electron session and
``opencode app`` does not exist as a CLI subcommand. The publish-workflow
checks pin the least-privilege permissions of every release job.

This module is deliberately text-based: PyYAML is available in the test env,
but parsing YAML would not expose the inline permission comments that document
why each scope exists.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PUBLISH = REPO_ROOT / ".github" / "workflows" / "publish.yml"
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

# Every publish.yml job is pinned exactly: extra scopes are over-privilege,
# missing scopes are a regression. Only update this map together with the job.
PUBLISH_PERMISSIONS: dict[str, set[str]] = {
    "resolve-ref": {"contents: read"},
    "build": {"contents: read"},
    "test-cross-platform": {"contents: read"},
    "gate-and-publish": {"contents: read", "issues: write"},
    "create-github-release": {"contents: write"},
    "on-failure": {"contents: read", "issues: write", "actions: write"},
}
BROAD_PERMISSIONS = re.compile(r"^\s+permissions:\s*(write-all|read-all|inherit)\b", re.MULTILINE)


def _workflow() -> str:
    assert CI.is_file(), f"{CI} is missing"
    return CI.read_text(encoding="utf-8")


def _publish_workflow() -> str:
    assert PUBLISH.is_file(), f"{PUBLISH} is missing"
    return PUBLISH.read_text(encoding="utf-8")


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


def _publish_job_ids(workflow: str) -> list[str]:
    jobs_at = re.search(r"^jobs:\s*$", workflow, re.MULTILINE)
    assert jobs_at is not None, "publish.yml has no jobs block"
    return [
        match.group(1)
        for match in re.finditer(
            r"^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$", workflow[jobs_at.end() :], re.MULTILINE
        )
    ]


def _job_permissions(job: str) -> set[str]:
    lines = job.splitlines()
    for index, line in enumerate(lines):
        if line != "    permissions:":
            continue
        found: set[str] = set()
        for following in lines[index + 1 :]:
            match = re.match(r"^      ([a-z][a-z0-9-]*):\s*(read|write|none)\b", following)
            if match:
                found.add(f"{match.group(1)}: {match.group(2)}")
                continue
            if following.strip() and not following.startswith("        "):
                break
        return found
    raise AssertionError("job has no permissions block")


def _assert_publish_least_privilege(workflow: str) -> None:
    assert re.search(r"^permissions:\s*\{\}\s*$", workflow, re.MULTILINE) is not None, (
        "publish.yml must deny all scopes at workflow level"
    )
    job_ids = _publish_job_ids(workflow)
    assert set(job_ids) == set(PUBLISH_PERMISSIONS), (
        f"unexpected publish jobs: {sorted(set(job_ids) ^ set(PUBLISH_PERMISSIONS))}"
    )
    for job_id in job_ids:
        job = _job_block(workflow, job_id)
        assert BROAD_PERMISSIONS.search(job) is None, f"{job_id} uses a broad permissions keyword"
        actual = _job_permissions(job)
        assert actual == PUBLISH_PERMISSIONS[job_id], (
            f"{job_id} expected {sorted(PUBLISH_PERMISSIONS[job_id])}, got {sorted(actual)}"
        )


def test_publish_workflow_permissions_are_least_privilege() -> None:
    _assert_publish_least_privilege(_publish_workflow())


def test_publish_permission_guard_detects_missing_actions_write() -> None:
    """Permanent RED control: remove the tracker scope and the guard must fail."""
    workflow = re.sub(
        r"^      actions: write.*\n", "", _publish_workflow(), count=1, flags=re.MULTILINE
    )
    assert "actions: write" not in workflow, "negative control did not strip the scope"
    with pytest.raises(AssertionError, match="on-failure"):
        _assert_publish_least_privilege(workflow)


def test_publish_tracker_persists_release_tag_with_narrow_scopes() -> None:
    tracker = _job_block(_publish_workflow(), "on-failure")
    assert "name: update-release-tracker" in tracker
    assert "if: failure()" in tracker
    assert "needs: [resolve-ref, build, test-cross-platform, gate-and-publish]" in tracker
    assert "python scripts/ci/update_issue.py" in tracker
    assert 'gh variable set LAST_RELEASE_TAG --body "$REF"' in tracker
    assert _job_permissions(tracker) == {"contents: read", "issues: write", "actions: write"}


def _assert_tracker_variable_write_is_best_effort(tracker: str) -> None:
    assert re.search(
        r'^[ \t]+gh variable set LAST_RELEASE_TAG --body "\$REF" \|\| '
        r'echo "::warning::[^\n]*LAST_RELEASE_TAG[^\n]*"$',
        tracker,
        re.MULTILINE,
    ), "LAST_RELEASE_TAG write must explicitly swallow failures with a warning"


def test_publish_tracker_variable_write_is_best_effort() -> None:
    """A 403 on the bookkeeping variable must not fail the release tracker."""
    tracker = _job_block(_publish_workflow(), "on-failure")
    assert re.search(r"^\s+set -euo pipefail\s*$", tracker, re.MULTILINE), (
        "tracker script must keep strict shell semantics so a failed issue update still fails"
    )
    assert re.search(r"^[ \t]+python scripts/ci/update_issue\.py[^\n|]*$", tracker, re.MULTILINE), (
        "the tracker issue update must stay strict (no shell fallback)"
    )
    _assert_tracker_variable_write_is_best_effort(tracker)


def test_publish_tracker_guard_detects_fatal_variable_write() -> None:
    """Permanent RED control: restore the fatal write and the guard must fail."""
    fatal = _publish_workflow().replace(
        'gh variable set LAST_RELEASE_TAG --body "$REF" || '
        'echo "::warning::Could not update LAST_RELEASE_TAG (continuing)"',
        'gh variable set LAST_RELEASE_TAG --body "$REF"',
    )
    assert '|| echo "::warning::' not in _job_block(fatal, "on-failure")
    with pytest.raises(AssertionError, match="LAST_RELEASE_TAG write must explicitly"):
        _assert_tracker_variable_write_is_best_effort(_job_block(fatal, "on-failure"))


def test_publish_release_job_needs_chain() -> None:
    release = _job_block(_publish_workflow(), "create-github-release")
    assert "if: github.event_name == 'push'" in release
    assert "needs: [resolve-ref, gate-and-publish]" in release
    assert "generate-notes" in release
    assert "gh release create" in release
    assert _job_permissions(release) == {"contents: write"}
