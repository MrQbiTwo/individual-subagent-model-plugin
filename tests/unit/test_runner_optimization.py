"""Static contract for the slow-runner optimizations in CI and Publish.

The timing evidence is in ``Windows ARM Runner Optimization.md`` (private
vault): the ARM ``Run full suite`` step was ~560s because ``npm ci`` ran
twice -- once in the runner script and again inside the ``serial_npm``
pytest group. These guards keep the cache, the install-skip and the
replacement entrypoint assertions in place, and keep the worker policy
shared across every runner instead of silently diverging on ARM.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = {
    "ci.yml": REPO_ROOT / ".github" / "workflows" / "ci.yml",
    "publish.yml": REPO_ROOT / ".github" / "workflows" / "publish.yml",
}
RUNNERS = (
    "ubuntu-24.04",
    "ubuntu-24.04-arm",
    "windows-latest",
    "macos-latest",
    "windows-11-arm",
)
# CI still gates all five runners; the release matrix has no ubuntu-24.04 leg
# because the built package is reused from the build job.
JOB_RUNNERS = {
    ("ci.yml", "test"): RUNNERS,
    ("ci.yml", "desktop_contract"): RUNNERS,
    ("publish.yml", "test-cross-platform"): RUNNERS[1:],
}
JOBS = tuple(JOB_RUNNERS)


def _workflow(name: str) -> str:
    return WORKFLOWS[name].read_text(encoding="utf-8")


def _job_block(text: str, job_id: str) -> str:
    lines = text.splitlines()
    heading = re.compile(rf"^  {re.escape(job_id)}:\s*$")
    for index, line in enumerate(lines):
        if heading.match(line):
            collected = [line]
            for following in lines[index + 1 :]:
                if re.match(r"^  [A-Za-z_][A-Za-z0-9_-]*:\s*$", following):
                    break
                collected.append(following)
            return "\n".join(collected)
    raise AssertionError(f"job {job_id!r} is missing from the workflow")


def _steps(job: str) -> list[str]:
    lines = job.splitlines()
    starts = [i for i, line in enumerate(lines) if re.match(r"^      - name:", line)]
    return [
        "\n".join(lines[start : starts[i + 1] if i + 1 < len(starts) else len(lines)])
        for i, start in enumerate(starts)
    ]


def _steps_named(job: str, needle: str) -> list[str]:
    return [step for step in _steps(job) if needle in step]


def _assert_cache(workflow: str, job_id: str) -> None:
    job = _job_block(_workflow(workflow), job_id)
    setup = _steps_named(job, "uses: actions/setup-node")
    assert setup, f"{workflow}/{job_id} has no setup-node step"
    for step in setup:
        assert re.search(r"^\s+cache:\s*['\"]?npm['\"]?\s*$", step, re.MULTILINE), step
        assert "cache-dependency-path: opencode/package-lock.json" in step


def _assert_install_not_repeated(workflow: str, job_id: str) -> None:
    job = _job_block(_workflow(workflow), job_id)
    full_suite = _steps_named(job, "Run full suite")
    assert len(full_suite) == 2, f"{workflow}/{job_id}: expected Unix + Windows steps"
    for step in full_suite:
        assert "OPENCODE_TEST_SKIP_INSTALL: '1'" in step, step


def _assert_entrypoints_checked(workflow: str, job_id: str) -> None:
    job = _job_block(_workflow(workflow), job_id)
    verify = _steps_named(job, "Verify built server entrypoints")
    assert len(verify) == 1, f"{workflow}/{job_id}: replacement assertion is missing"
    step = verify[0]
    for expected in ("dist/index.js", "dist/rpc.js", "dist/tui.js", "dist/gui-experimental.cjs"):
        assert expected in step, (expected, step)
    assert "node -e" in step, "ARM import smoke check must still import the built entrypoint"


def _assert_shared_worker_policy(text: str) -> None:
    assert "PYTEST_XDIST_N" not in text, "no workflow may override the PowerShell worker count"
    assert "PYTEST_XDIST_WORKERS" not in text, "no workflow may override the Bash worker count"
    ps1 = (REPO_ROOT / "scripts" / "run_tests.ps1").read_text(encoding="utf-8")
    sh = (REPO_ROOT / "scripts" / "run_tests.sh").read_text(encoding="utf-8")
    assert '$env:PYTEST_XDIST_N = "4"' in ps1
    assert 'workers="${PYTEST_XDIST_WORKERS:-4}"' in sh


def test_matrix_jobs_keep_every_runner_label() -> None:
    for workflow, job_id in JOBS:
        job = _job_block(_workflow(workflow), job_id)
        for runner in JOB_RUNNERS[(workflow, job_id)]:
            assert re.search(rf"^\s+- {re.escape(runner)}\s*$", job, re.MULTILINE), (
                workflow,
                job_id,
                runner,
            )
        assert "runs-on: ${{ matrix.os }}" in job


def test_npm_cache_is_enabled_on_ci_matrix_jobs() -> None:
    _assert_cache("ci.yml", "test")
    _assert_cache("ci.yml", "desktop_contract")


def test_release_matrix_keeps_cache_disabled() -> None:
    """zizmor forbids caches in a workflow that publishes runtime artifacts."""
    job = _job_block(_workflow("publish.yml"), "test-cross-platform")
    setup = _steps_named(job, "uses: actions/setup-node")
    assert setup
    for step in setup:
        assert "package-manager-cache: false" in step
        assert "cache-dependency-path" not in step
        assert not re.search(r"^\s+cache:\s*npm\s*$", step, re.MULTILINE)


def test_ci_does_not_repeat_npm_install_inside_pytest() -> None:
    for workflow, job_id in JOBS:
        _assert_install_not_repeated(workflow, job_id)


def test_skipped_install_tests_keep_their_assertions() -> None:
    for workflow, job_id in JOBS:
        _assert_entrypoints_checked(workflow, job_id)


def test_worker_count_is_shared_not_runner_specific() -> None:
    for workflow in WORKFLOWS:
        _assert_shared_worker_policy(_workflow(workflow))


def test_worker_override_guard_is_strict() -> None:
    """Permanent RED control: an ARM-only worker override must be rejected."""
    mutated = _workflow("ci.yml").replace(
        "          node-version: '24'\n",
        "          node-version: '24'\n          PYTEST_XDIST_N: '2'\n",
        count=1,
    )
    assert "PYTEST_XDIST_N" in mutated, "negative control did not inject the override"
    with pytest.raises(AssertionError, match="PYTEST_XDIST_N"):
        _assert_shared_worker_policy(mutated)
