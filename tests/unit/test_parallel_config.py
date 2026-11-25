"""Static checks for the parallel test configuration and worker-isolated ports."""

from __future__ import annotations

from pathlib import Path

from conftest import _reserve_port

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_pyproject_declares_xdist_and_loadgroup() -> None:
    text = (REPO_ROOT / "tests" / "pyproject.toml").read_text(encoding="utf-8")

    assert "pytest-xdist>=3.6,<4" in text
    assert "--dist=loadgroup" in text


def test_requirements_shim_declares_xdist() -> None:
    text = (REPO_ROOT / "tests" / "requirements.txt").read_text(encoding="utf-8")

    assert "pytest-xdist>=3.6,<4" in text


def test_pytest_is_capped_below_nine_for_xdist_loadgroup() -> None:
    """xdist 3.8 patches ``_nodeid``; pytest 9 reads ``_id`` and ignores the group."""
    for filename in ("pyproject.toml", "requirements.txt"):
        text = (REPO_ROOT / "tests" / filename).read_text(encoding="utf-8")
        assert "pytest>=8,<9" in text, filename


def test_runner_scripts_pass_parallel_flags() -> None:
    scripts = (
        REPO_ROOT / "scripts" / "run_tests.ps1",
        REPO_ROOT / "scripts" / "run_tests.sh",
    )
    for script in scripts:
        text = script.read_text(encoding="utf-8")
        assert "-n" in text
        assert "--dist=loadgroup" in text


def test_reserve_port_is_worker_scoped() -> None:
    master_socket, master_port = _reserve_port("master")
    worker_socket, worker_port = _reserve_port("gw0")
    second_worker_socket, second_worker_port = _reserve_port("gw1")
    try:
        assert 41000 <= master_port <= 41099
        assert 41100 <= worker_port <= 41199
        assert 41200 <= second_worker_port <= 41299
    finally:
        master_socket.close()
        worker_socket.close()
        second_worker_socket.close()
