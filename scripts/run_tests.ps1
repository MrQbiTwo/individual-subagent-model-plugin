# Native PowerShell test runner for Windows.
# Uses only tools available on Windows; no compatibility-layer calls.
$ErrorActionPreference = "Stop"

Write-Host "Runner shell: PowerShell $($PSVersionTable.PSVersion)"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

if ($null -eq (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "python >= 3.12.3 is required"
}

& python -c "import sys; assert sys.version_info >= (3,12,3), 'Python 3.12.3+ is required'"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Prefer uv when it is available; otherwise fall back to a local virtual
# environment so the runner also works on bare CI images without uv.
$useUv = $null -ne (Get-Command uv -ErrorAction SilentlyContinue)
if ($useUv) {
    & uv sync --project tests --all-groups
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    . .\.venv\Scripts\Activate.ps1
    & python -m pip install --disable-pip-version-check -r tests/requirements.txt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

& npm ci --prefix opencode
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& npm run build --prefix opencode
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# The Codex adapter has its own lock file and two-stage build; its compiled
# probes are exercised by the codex_cli / codex_app contract tests below.
& npm ci --prefix codex
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& npm run build --prefix codex
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

New-Item -ItemType Directory -Force -Path reports | Out-Null
if (-not $env:PYTEST_XDIST_N) { $env:PYTEST_XDIST_N = "4" }
$testFilter = "unit or integration or e2e or universal or contract or opencode_cli or opencode_desktop or codex_cli or codex_app"
if ($useUv) {
    & uv run --project tests python -m pytest tests -n $env:PYTEST_XDIST_N --dist=loadgroup -m $testFilter --junitxml=reports/junit.xml
} else {
    & python -m pytest tests -n $env:PYTEST_XDIST_N --dist=loadgroup -m $testFilter --junitxml=reports/junit.xml
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$nodeVersion = (& node --version).Trim().TrimStart("v")
if ($useUv) {
    & uv run --project tests python scripts/ci/check_engines.py $nodeVersion ">=22.0.0" "false"
} else {
    & python scripts/ci/check_engines.py $nodeVersion ">=22.0.0" "false"
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "All tests passed. JUnit report: reports/junit.xml"
