param(
  [switch]$E2E,
  [switch]$Unit,
  [switch]$All
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$venvPython = Join-Path $repoRoot "venv\\Scripts\\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

if ($E2E -and $Unit) {
  Write-Host "Choose only one: -E2E or -Unit (or use -All)." -ForegroundColor Yellow
  exit 2
}

if ($E2E) {
  & $python -m pytest -m e2e -vv
  exit $LASTEXITCODE
}

if ($All) {
  & $python -m pytest -vv
  exit $LASTEXITCODE
}

# Default: unit/integration tests (non-E2E)
& $python -m pytest -m "not e2e" -vv
exit $LASTEXITCODE
