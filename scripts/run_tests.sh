#!/usr/bin/env bash
# Native Bash test runner for Linux and macOS.
# Uses only tools available on those platforms; no compatibility-layer calls.
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
cd "${repo_root}"

python_bin="$(command -v python3 || true)"
if [[ -z "${python_bin}" ]]; then
  echo "python3 >= 3.12.3 is required" >&2
  exit 1
fi

"${python_bin}" - <<'PY'
import sys

required = (3, 12, 3)
if sys.version_info < required:
    wanted = ".".join(str(part) for part in required)
    raise SystemExit(f"Python {wanted}+ is required, found {sys.version.split()[0]}")
PY

# Prefer uv when it is available; otherwise fall back to a local virtual
# environment so the runner also works on bare CI images without uv.
python_launcher=()
if command -v uv >/dev/null 2>&1; then
  uv sync --project tests --all-groups
  python_launcher=(uv run --project tests python)
else
  "${python_bin}" -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --disable-pip-version-check -r tests/requirements.txt
  python_launcher=(python)
fi

npm ci --prefix opencode
npm run build --prefix opencode

# The Codex adapter has its own lock file and two-stage build; its compiled
# probes are exercised by the codex_cli / codex_app contract tests below.
npm ci --prefix codex
npm run build --prefix codex

mkdir -p reports
workers="${PYTEST_XDIST_WORKERS:-4}"
"${python_launcher[@]}" -m pytest tests \
  -n "$workers" --dist=loadgroup \
  -m "unit or integration or e2e or universal or contract or opencode_cli or opencode_desktop or codex_cli or codex_app" \
  --junitxml=reports/junit.xml

node_version="$(node --version)"
"${python_launcher[@]}" scripts/ci/check_engines.py \
  "${node_version#v}" ">=22.0.0" "false"

echo "All tests passed. JUnit report: reports/junit.xml"
