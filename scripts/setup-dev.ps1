param(
  [switch]$SkipPlaywright
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$venvDir = Join-Path $repoRoot "venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
  Write-Host "Creating virtual environment: $venvDir" -ForegroundColor Cyan
  python -m venv $venvDir
}

Write-Host "Upgrading pip..." -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Installing runtime and developer requirements..." -ForegroundColor Cyan
& $venvPython -m pip install -r (Join-Path $repoRoot "requirements.txt") -r (Join-Path $repoRoot "requirements-dev.txt")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $SkipPlaywright) {
  Write-Host "Installing Playwright browsers..." -ForegroundColor Cyan
  & $venvPython -m playwright install
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Developer environment is ready." -ForegroundColor Green
