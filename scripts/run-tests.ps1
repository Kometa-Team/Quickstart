param(
  [switch]$E2E,
  [switch]$Unit,
  [switch]$RatingsMatrix,
  [switch]$RatingsArtifacts,
  [switch]$NoCapture,
  [string]$RatingsProfileOrder,
  [string]$RatingsWithKometa,
  [string]$RatingsFailOnDiff,
  [double]$RatingsDiffThresholdPercent = -1,
  [int]$RatingsCaseOffset = -1,
  [int]$RatingsCaseLimit = -1,
  [string]$RatingsExecutionMode,
  [int]$RatingsChunkSize = -1,
  [int]$RatingsShowLayerReadyTimeoutMs = -1,
  [int]$RatingsShowLibraryLoadTimeoutMs = -1,
  [int]$RatingsRandomCount = -1,
  [string]$RatingsRandomSeed,
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
#   "ratings_artifact_dir": "artifacts/ratings-matrix/local",
#   "ratings_profile_order": "show,episode,movie",
#   "ratings_with_kometa": true,
#   "ratings_fail_on_diff": false,
#   "ratings_diff_threshold_percent": 0.0,
#   "ratings_execution_mode": "batch",
#   "ratings_chunk_size": 12,
#   "ratings_show_layer_ready_timeout_ms": 3000,
#   "ratings_show_library_load_timeout_ms": 40000,
#   "ratings_random_count": 0,
#   "ratings_random_seed": "",
#   "ratings_case_offset": 0,
#   "ratings_case_limit": 0
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
$resolvedRatingsProfileOrder = if ($RatingsProfileOrder) { $RatingsProfileOrder } elseif ($env:RATINGS_MATRIX_PROFILE_ORDER) { $env:RATINGS_MATRIX_PROFILE_ORDER } else { $localConfig["ratings_profile_order"] }
$resolvedRatingsWithKometa = if ($RatingsWithKometa) { $RatingsWithKometa } elseif ($env:RATINGS_MATRIX_WITH_KOMETA) { $env:RATINGS_MATRIX_WITH_KOMETA } elseif ($localConfig.ContainsKey("ratings_with_kometa")) { [string]$localConfig["ratings_with_kometa"] } else { $null }
$resolvedRatingsFailOnDiff = if ($RatingsFailOnDiff) { $RatingsFailOnDiff } elseif ($env:RATINGS_MATRIX_FAIL_ON_DIFF) { $env:RATINGS_MATRIX_FAIL_ON_DIFF } elseif ($localConfig.ContainsKey("ratings_fail_on_diff")) { [string]$localConfig["ratings_fail_on_diff"] } else { $null }
$resolvedRatingsDiffThreshold = if ($RatingsDiffThresholdPercent -ge 0) { $RatingsDiffThresholdPercent } elseif ($env:RATINGS_MATRIX_DIFF_THRESHOLD_PERCENT) { [double]$env:RATINGS_MATRIX_DIFF_THRESHOLD_PERCENT } elseif ($localConfig.ContainsKey("ratings_diff_threshold_percent")) { [double]$localConfig["ratings_diff_threshold_percent"] } else { $null }
$resolvedRatingsExecutionMode = if ($RatingsExecutionMode) { $RatingsExecutionMode } elseif ($env:RATINGS_MATRIX_EXECUTION_MODE) { $env:RATINGS_MATRIX_EXECUTION_MODE } else { $localConfig["ratings_execution_mode"] }
$resolvedRatingsChunkSize = if ($RatingsChunkSize -ge 0) { $RatingsChunkSize } elseif ($env:RATINGS_MATRIX_CHUNK_SIZE) { [int]$env:RATINGS_MATRIX_CHUNK_SIZE } elseif ($localConfig.ContainsKey("ratings_chunk_size")) { [int]$localConfig["ratings_chunk_size"] } else { $null }
$resolvedRatingsShowLayerReadyTimeoutMs = if ($RatingsShowLayerReadyTimeoutMs -ge 0) { $RatingsShowLayerReadyTimeoutMs } elseif ($env:RATINGS_SHOW_LAYER_READY_TIMEOUT_MS) { [int]$env:RATINGS_SHOW_LAYER_READY_TIMEOUT_MS } elseif ($localConfig.ContainsKey("ratings_show_layer_ready_timeout_ms")) { [int]$localConfig["ratings_show_layer_ready_timeout_ms"] } else { $null }
$resolvedRatingsShowLibraryLoadTimeoutMs = if ($RatingsShowLibraryLoadTimeoutMs -ge 0) { $RatingsShowLibraryLoadTimeoutMs } elseif ($env:RATINGS_SHOW_LIBRARY_LOAD_TIMEOUT_MS) { [int]$env:RATINGS_SHOW_LIBRARY_LOAD_TIMEOUT_MS } elseif ($localConfig.ContainsKey("ratings_show_library_load_timeout_ms")) { [int]$localConfig["ratings_show_library_load_timeout_ms"] } else { $null }
$resolvedRatingsRandomCount = if ($RatingsRandomCount -ge 0) { $RatingsRandomCount } elseif ($env:RATINGS_MATRIX_RANDOM_COUNT) { [int]$env:RATINGS_MATRIX_RANDOM_COUNT } elseif ($localConfig.ContainsKey("ratings_random_count")) { [int]$localConfig["ratings_random_count"] } else { $null }
$resolvedRatingsRandomSeed = if ($RatingsRandomSeed) { $RatingsRandomSeed } elseif ($env:RATINGS_MATRIX_RANDOM_SEED) { $env:RATINGS_MATRIX_RANDOM_SEED } else { $localConfig["ratings_random_seed"] }
$resolvedRatingsCaseOffset = if ($RatingsCaseOffset -ge 0) { $RatingsCaseOffset } elseif ($env:RATINGS_MATRIX_CASE_OFFSET) { [int]$env:RATINGS_MATRIX_CASE_OFFSET } elseif ($localConfig.ContainsKey("ratings_case_offset")) { [int]$localConfig["ratings_case_offset"] } else { $null }
$resolvedRatingsCaseLimit = if ($RatingsCaseLimit -ge 0) { $RatingsCaseLimit } elseif ($env:RATINGS_MATRIX_CASE_LIMIT) { [int]$env:RATINGS_MATRIX_CASE_LIMIT } elseif ($localConfig.ContainsKey("ratings_case_limit")) { [int]$localConfig["ratings_case_limit"] } else { $null }

if ($null -ne $resolvedRatingsProfileOrder -and "$resolvedRatingsProfileOrder".Trim() -ne "") {
  if ($resolvedRatingsProfileOrder -is [array]) {
    $env:RATINGS_MATRIX_PROFILE_ORDER = ($resolvedRatingsProfileOrder -join ",")
  } else {
    $env:RATINGS_MATRIX_PROFILE_ORDER = [string]$resolvedRatingsProfileOrder
  }
}
if ($null -ne $resolvedRatingsCaseOffset) {
  $env:RATINGS_MATRIX_CASE_OFFSET = [string]$resolvedRatingsCaseOffset
}
if ($null -ne $resolvedRatingsCaseLimit) {
  $env:RATINGS_MATRIX_CASE_LIMIT = [string]$resolvedRatingsCaseLimit
}
if ($null -ne $resolvedRatingsWithKometa -and "$resolvedRatingsWithKometa".Trim() -ne "") {
  $env:RATINGS_MATRIX_WITH_KOMETA = [string]$resolvedRatingsWithKometa
}
if ($null -ne $resolvedRatingsFailOnDiff -and "$resolvedRatingsFailOnDiff".Trim() -ne "") {
  $env:RATINGS_MATRIX_FAIL_ON_DIFF = [string]$resolvedRatingsFailOnDiff
}
if ($null -ne $resolvedRatingsDiffThreshold) {
  $env:RATINGS_MATRIX_DIFF_THRESHOLD_PERCENT = [string]$resolvedRatingsDiffThreshold
}
if ($null -ne $resolvedRatingsExecutionMode -and "$resolvedRatingsExecutionMode".Trim() -ne "") {
  $env:RATINGS_MATRIX_EXECUTION_MODE = [string]$resolvedRatingsExecutionMode
}
if ($null -ne $resolvedRatingsChunkSize) {
  $env:RATINGS_MATRIX_CHUNK_SIZE = [string]$resolvedRatingsChunkSize
}
if ($null -ne $resolvedRatingsShowLayerReadyTimeoutMs) {
  $env:RATINGS_SHOW_LAYER_READY_TIMEOUT_MS = [string]$resolvedRatingsShowLayerReadyTimeoutMs
}
if ($null -ne $resolvedRatingsShowLibraryLoadTimeoutMs) {
  $env:RATINGS_SHOW_LIBRARY_LOAD_TIMEOUT_MS = [string]$resolvedRatingsShowLibraryLoadTimeoutMs
}
if ($null -ne $resolvedRatingsRandomCount) {
  $env:RATINGS_MATRIX_RANDOM_COUNT = [string]$resolvedRatingsRandomCount
}
if ($null -ne $resolvedRatingsRandomSeed -and "$resolvedRatingsRandomSeed".Trim() -ne "") {
  $env:RATINGS_MATRIX_RANDOM_SEED = [string]$resolvedRatingsRandomSeed
}

if (@($E2E, $Unit, $RatingsMatrix, $RatingsArtifacts).Where({ $_ }).Count -gt 1) {
  Write-Host "Choose only one: -E2E, -Unit, -RatingsMatrix, or -RatingsArtifacts (or use -All)." -ForegroundColor Yellow
  exit 2
}

if ($E2E) {
  if ($NoCapture) {
    & $python -m pytest -m e2e -vv -s
  } else {
    & $python -m pytest -m e2e -vv
  }
  exit $LASTEXITCODE
}

if ($RatingsMatrix) {
  if ($resolvedRatingsMovieLibrary) { $env:RATINGS_MATRIX_MOVIE_LIBRARY = $resolvedRatingsMovieLibrary }
  if ($resolvedRatingsShowLibrary) { $env:RATINGS_MATRIX_SHOW_LIBRARY = $resolvedRatingsShowLibrary }
  if ($NoCapture) {
    & $python -m pytest -m ratings_matrix -vv -s
  } else {
    & $python -m pytest -m ratings_matrix -vv
  }
  exit $LASTEXITCODE
}

if ($RatingsArtifacts) {
  if ($resolvedRatingsMovieLibrary) { $env:RATINGS_MATRIX_MOVIE_LIBRARY = $resolvedRatingsMovieLibrary }
  if ($resolvedRatingsShowLibrary) { $env:RATINGS_MATRIX_SHOW_LIBRARY = $resolvedRatingsShowLibrary }
  if ($resolvedRatingsArtifactDir) { $env:RATINGS_MATRIX_ARTIFACT_DIR = $resolvedRatingsArtifactDir }
  if ($NoCapture) {
    & $python -m pytest -m ratings_artifacts -vv -s
  } else {
    # Artifacts runs are long and benefit from live progress output.
    & $python -m pytest -m ratings_artifacts -vv -s
  }
  exit $LASTEXITCODE
}

if ($All) {
  if ($NoCapture) {
    & $python -m pytest -vv -s
  } else {
    & $python -m pytest -vv
  }
  exit $LASTEXITCODE
}

# Default: unit/integration tests (non-E2E)
if ($NoCapture) {
  & $python -m pytest -m "not e2e and not ratings_matrix" -vv -s
} else {
  & $python -m pytest -m "not e2e and not ratings_matrix" -vv
}
exit $LASTEXITCODE
