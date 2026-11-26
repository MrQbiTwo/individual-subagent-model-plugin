"""Static contract for the Codex build checks in CI and Publish.

The Codex adapter is built alongside OpenCode on every CI runner and in the
release cross-platform matrix. These guards are text-based: they pin the
npm cache path list, the built-entrypoint smoke checks, the Codex failure
label and the declarative label inventory without spawning npm or Node.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PUBLISH = REPO_ROOT / ".github" / "workflows" / "publish.yml"
LABELS = REPO_ROOT / ".github" / "labels.yml"

CI_JOBS = ("test", "desktop_contract")
LOCKFILES = ("opencode/package-lock.json", "codex/package-lock.json")
CODEX_ENTRYPOINTS = (
    "test -f dist/index.js",
    "test -f dist/catalog.js",
    "test -f dist/universal/index.js",
    "node -e \"import('./dist/index.js')\"",
)
LABEL_NAMES = (
    "bug",
    "ci-codex",
    "ci-compat",
    "ci-release",
    "ci-untested",
    "codex",
    "dependencies",
    "enhancement",
    "github-actions",
    "opencode",
    "opencode-verison-support",
    "python:uv",
    "triage",
    "ui-bug",
)
JOB_KEY = re.compile(r"^  [A-Za-z_][A-Za-z0-9_-]*:\s*$")
PINNED_ACTION = re.compile(r"@[0-9a-f]{40}$")


def _read(path: Path) -> str:
    assert path.is_file(), f"{path.relative_to(REPO_ROOT)} is missing"
    return path.read_text(encoding="utf-8")


def _job_block(text: str, job_id: str) -> str:
    heading = re.compile(rf"^  {re.escape(job_id)}:\s*$")
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if heading.match(line):
            collected = [line]
            for following in lines[index + 1 :]:
                if JOB_KEY.match(following):
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


def _steps_named(job: str, name: str) -> list[str]:
    heading = f"      - name: {name}"
    return [step for step in _steps(job) if step.splitlines()[0] == heading]


def test_ci_jobs_cache_both_lockfiles() -> None:
    for job_id in CI_JOBS:
        job = _job_block(_read(CI), job_id)
        setup = [step for step in _steps(job) if "uses: actions/setup-node" in step]
        assert len(setup) == 1, f"{job_id}: expected exactly one setup-node step"
        step = setup[0]
        assert re.search(r"^\s+cache: 'npm'\s*$", step, re.MULTILINE), step
        assert "cache-dependency-path: opencode/package-lock.json" in step, step
        assert re.search(r"^\s+cache-dependency-path: \|\s*$", step, re.MULTILINE), step
        block = step.split("cache-dependency-path: |", 1)[1]
        cached = re.findall(r"^ {12}(\S+)\s*$", block, re.MULTILINE)
        for lockfile in LOCKFILES:
            assert lockfile in cached, (job_id, lockfile, cached)


def test_ci_jobs_verify_built_codex_entrypoints() -> None:
    for job_id in CI_JOBS:
        job = _job_block(_read(CI), job_id)
        verify = _steps_named(job, "Verify built Codex entrypoints")
        assert len(verify) == 1, f"{job_id}: Codex entrypoint check is missing or duplicated"
        step = verify[0]
        assert re.search(r"^\s+shell: bash\s*$", step, re.MULTILINE), step
        assert "working-directory: ./codex" in step, step
        for assertion in CODEX_ENTRYPOINTS:
            assert assertion in step, (job_id, assertion, step)


def test_ci_failure_trackers_are_labelled_for_codex() -> None:
    for job_id in CI_JOBS:
        job = _job_block(_read(CI), job_id)
        trackers = _steps_named(job, "Update the untested-branch failure tracker")
        assert len(trackers) == 1, f"{job_id}: failure tracker is missing"
        assert "LABELS: bug,github-actions,ci-untested,codex" in trackers[0], trackers[0]
        assert "run: python scripts/ci/update_issue.py" in trackers[0], trackers[0]


def test_publish_cross_platform_verifies_codex_artifact() -> None:
    job = _job_block(_read(PUBLISH), "test-cross-platform")
    checks = [step for step in _steps(job) if "codex/dist/index.js" in step]
    assert len(checks) == 1, "release matrix must verify the built Codex artifact once per runner"
    step = checks[0]
    assert "test -f codex/dist/index.js" in step, step
    assert "node -e \"import('./codex/dist/index.js')\"" in step, step
    assert "package-manager-cache: false" in job, "release cache must stay disabled"
    assert "cache-dependency-path" not in job, "release job must not add a cache path"
    assert not re.search(r"^\s+cache:\s*npm\s*$", job, re.MULTILINE), step


def test_labels_inventory_is_complete_and_unique() -> None:
    text = _read(LABELS)
    names = re.findall(r"^-\s+name:\s*(\S+)\s*$", text, re.MULTILINE)
    assert names, ".github/labels.yml has no label entries"
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert not duplicates, f"duplicate labels: {duplicates}"
    assert set(names) == set(LABEL_NAMES), (
        f"label inventory mismatch: missing {sorted(set(LABEL_NAMES) - set(names))}, "
        f"extra {sorted(set(names) - set(LABEL_NAMES))}"
    )
    for required in ("codex", "ci-codex", "triage"):
        assert required in names, required
    colors = re.findall(
        r"^\s+color:\s*[\"']?([0-9A-Fa-f]{6})[\"']?\s*$", text, re.MULTILINE
    )
    assert len(colors) == len(LABEL_NAMES), "every label needs a 6-hex color"
    descriptions = re.findall(r"^\s+description:\s*\S", text, re.MULTILINE)
    assert len(descriptions) == len(LABEL_NAMES), "every label needs a description"


@pytest.mark.parametrize("path", [CI, PUBLISH])
def test_workflow_actions_are_sha_pinned(path: Path) -> None:
    uses = re.findall(r"^\s+uses:\s*(\S+)", _read(path), re.MULTILINE)
    assert uses, f"{path.name} has no pinned actions"
    for action in uses:
        assert PINNED_ACTION.search(action), f"action is not SHA-pinned: {action}"
