param(
  [switch]$E2E,
  [switch]$Unit,
  [switch]$RatingsMatrix,
  [switch]$RatingsArtifacts,
  [string]$RatingsMovieLibrary,
  [string]$RatingsShowLibrary,
  [string]$RatingsArtifactDir,
  [switch]$All
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$venvPython = Join-Path $repoRoot "venv\\Scripts\\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

# Optional local config file for per-user defaults:
# scripts/run-tests.config.json
# {
#   "ratings_movie_library": "TestMovies-4k",
#   "ratings_show_library": "TestTV Shows - 4k",
#   "ratings_artifact_dir": "artifacts/ratings-matrix/local"
# }
$localConfigPath = Join-Path $PSScriptRoot "run-tests.config.json"
$localConfig = @{}
if (Test-Path $localConfigPath) {
  try {
    $localConfig = Get-Content -Path $localConfigPath -Raw | ConvertFrom-Json -AsHashtable
  } catch {
    Write-Host "Warning: Failed to parse $localConfigPath. Ignoring local config." -ForegroundColor Yellow
  }
}

$resolvedRatingsMovieLibrary = if ($RatingsMovieLibrary) { $RatingsMovieLibrary } elseif ($env:RATINGS_MATRIX_MOVIE_LIBRARY) { $env:RATINGS_MATRIX_MOVIE_LIBRARY } else { $localConfig["ratings_movie_library"] }
$resolvedRatingsShowLibrary = if ($RatingsShowLibrary) { $RatingsShowLibrary } elseif ($env:RATINGS_MATRIX_SHOW_LIBRARY) { $env:RATINGS_MATRIX_SHOW_LIBRARY } else { $localConfig["ratings_show_library"] }
$resolvedRatingsArtifactDir = if ($RatingsArtifactDir) { $RatingsArtifactDir } elseif ($env:RATINGS_MATRIX_ARTIFACT_DIR) { $env:RATINGS_MATRIX_ARTIFACT_DIR } else { $localConfig["ratings_artifact_dir"] }

if (@($E2E, $Unit, $RatingsMatrix, $RatingsArtifacts).Where({ $_ }).Count -gt 1) {
  Write-Host "Choose only one: -E2E, -Unit, -RatingsMatrix, or -RatingsArtifacts (or use -All)." -ForegroundColor Yellow
  exit 2
}

if ($E2E) {
  & $python -m pytest -m e2e -vv
  exit $LASTEXITCODE
}

if ($RatingsMatrix) {
  if ($resolvedRatingsMovieLibrary) { $env:RATINGS_MATRIX_MOVIE_LIBRARY = $resolvedRatingsMovieLibrary }
  if ($resolvedRatingsShowLibrary) { $env:RATINGS_MATRIX_SHOW_LIBRARY = $resolvedRatingsShowLibrary }
  & $python -m pytest -m ratings_matrix -vv
  exit $LASTEXITCODE
}

if ($RatingsArtifacts) {
  if ($resolvedRatingsMovieLibrary) { $env:RATINGS_MATRIX_MOVIE_LIBRARY = $resolvedRatingsMovieLibrary }
  if ($resolvedRatingsShowLibrary) { $env:RATINGS_MATRIX_SHOW_LIBRARY = $resolvedRatingsShowLibrary }
  if ($resolvedRatingsArtifactDir) { $env:RATINGS_MATRIX_ARTIFACT_DIR = $resolvedRatingsArtifactDir }
  & $python -m pytest -m ratings_artifacts -vv
  exit $LASTEXITCODE
}

if ($All) {
  & $python -m pytest -vv
  exit $LASTEXITCODE
}

# Default: unit/integration tests (non-E2E)
& $python -m pytest -m "not e2e and not ratings_matrix" -vv
exit $LASTEXITCODE
