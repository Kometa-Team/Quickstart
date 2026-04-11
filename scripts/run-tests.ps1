param(
  [switch]$E2E,
  [switch]$Unit,
  [switch]$RatingsMatrix,
  [switch]$RatingsArtifacts,
  [switch]$NoCapture,
  [string]$RatingsProfileOrder,
  [string]$RatingsWithKometa,
  [string]$RatingsFailOnDiff,
  [string]$RatingsDiffIgnoreAlpha,
  [string]$RatingsIncludeNudges,
  [string]$RatingsNudgeProfiles,
  [string]$RatingsNudgeApplyTo,
  [string]$RatingsDiffUseSlotThresholds,
  [double]$RatingsDiffThresholdPercent = -1,
  [double]$RatingsDiffThresholdOneSlotPercent = -1,
  [double]$RatingsDiffThresholdTwoSlotPercent = -1,
  [double]$RatingsDiffThresholdThreeSlotPercent = -1,
  [int]$RatingsCaseOffset = -1,
  [int]$RatingsCaseLimit = -1,
  [string]$RatingsCaseIds,
  [string]$RatingsCaseIdsFile,
  [string]$RatingsExecutionMode,
  [int]$RatingsChunkSize = -1,
  [int]$RatingsShowLayerReadyTimeoutMs = -1,
  [int]$RatingsShowLibraryLoadTimeoutMs = -1,
  [int]$RatingsLibraryLoadRetries = -1,
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
#   "ratings_diff_ignore_alpha": true,
#   "ratings_include_nudges": false,
#   "ratings_nudge_profiles": "none,hv+15",
#   "ratings_nudge_apply_to": "enabled_slots",
#   "ratings_diff_use_slot_thresholds": true,
#   "ratings_diff_threshold_percent": 0.0,
#   "ratings_diff_threshold_one_slot_percent": 0.8,
#   "ratings_diff_threshold_two_slot_percent": 1.5,
#   "ratings_diff_threshold_three_slot_percent": 2.8,
#   "ratings_execution_mode": "batch",
#   "ratings_chunk_size": 12,
#   "ratings_show_layer_ready_timeout_ms": 3000,
#   "ratings_show_library_load_timeout_ms": 40000,
#   "ratings_library_load_retries": 3,
#   "ratings_random_count": 0,
#   "ratings_random_seed": "",
#   "ratings_case_offset": 0,
#   "ratings_case_limit": 0,
#   "ratings_case_ids": "",
#   "ratings_case_ids_file": ""
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

$resolvedRatingsMovieLibrary = if ($RatingsMovieLibrary) { $RatingsMovieLibrary } elseif ($localConfig.ContainsKey("ratings_movie_library")) { $localConfig["ratings_movie_library"] } elseif ($env:RATINGS_MATRIX_MOVIE_LIBRARY) { $env:RATINGS_MATRIX_MOVIE_LIBRARY } else { $null }
$resolvedRatingsShowLibrary = if ($RatingsShowLibrary) { $RatingsShowLibrary } elseif ($localConfig.ContainsKey("ratings_show_library")) { $localConfig["ratings_show_library"] } elseif ($env:RATINGS_MATRIX_SHOW_LIBRARY) { $env:RATINGS_MATRIX_SHOW_LIBRARY } else { $null }
$resolvedRatingsArtifactDir = if ($RatingsArtifactDir) { $RatingsArtifactDir } elseif ($localConfig.ContainsKey("ratings_artifact_dir")) { $localConfig["ratings_artifact_dir"] } elseif ($env:RATINGS_MATRIX_ARTIFACT_DIR) { $env:RATINGS_MATRIX_ARTIFACT_DIR } else { $null }
$resolvedRatingsProfileOrder = if ($RatingsProfileOrder) { $RatingsProfileOrder } elseif ($localConfig.ContainsKey("ratings_profile_order")) { $localConfig["ratings_profile_order"] } elseif ($env:RATINGS_MATRIX_PROFILE_ORDER) { $env:RATINGS_MATRIX_PROFILE_ORDER } else { $null }
$resolvedRatingsWithKometa = if ($RatingsWithKometa) { $RatingsWithKometa } elseif ($localConfig.ContainsKey("ratings_with_kometa")) { [string]$localConfig["ratings_with_kometa"] } elseif ($env:RATINGS_MATRIX_WITH_KOMETA) { $env:RATINGS_MATRIX_WITH_KOMETA } else { $null }
$resolvedRatingsFailOnDiff = if ($RatingsFailOnDiff) { $RatingsFailOnDiff } elseif ($localConfig.ContainsKey("ratings_fail_on_diff")) { [string]$localConfig["ratings_fail_on_diff"] } elseif ($env:RATINGS_MATRIX_FAIL_ON_DIFF) { $env:RATINGS_MATRIX_FAIL_ON_DIFF } else { $null }
$resolvedRatingsDiffIgnoreAlpha = if ($RatingsDiffIgnoreAlpha) { $RatingsDiffIgnoreAlpha } elseif ($localConfig.ContainsKey("ratings_diff_ignore_alpha")) { [string]$localConfig["ratings_diff_ignore_alpha"] } elseif ($env:RATINGS_MATRIX_DIFF_IGNORE_ALPHA) { $env:RATINGS_MATRIX_DIFF_IGNORE_ALPHA } else { $null }
$resolvedRatingsIncludeNudges = if ($RatingsIncludeNudges) { $RatingsIncludeNudges } elseif ($localConfig.ContainsKey("ratings_include_nudges")) { [string]$localConfig["ratings_include_nudges"] } elseif ($env:RATINGS_MATRIX_INCLUDE_NUDGES) { $env:RATINGS_MATRIX_INCLUDE_NUDGES } else { $null }
$resolvedRatingsNudgeProfiles = if ($RatingsNudgeProfiles) { $RatingsNudgeProfiles } elseif ($localConfig.ContainsKey("ratings_nudge_profiles")) { [string]$localConfig["ratings_nudge_profiles"] } elseif ($env:RATINGS_MATRIX_NUDGE_PROFILES) { $env:RATINGS_MATRIX_NUDGE_PROFILES } else { $null }
$resolvedRatingsNudgeApplyTo = if ($RatingsNudgeApplyTo) { $RatingsNudgeApplyTo } elseif ($localConfig.ContainsKey("ratings_nudge_apply_to")) { [string]$localConfig["ratings_nudge_apply_to"] } elseif ($env:RATINGS_MATRIX_NUDGE_APPLY_TO) { $env:RATINGS_MATRIX_NUDGE_APPLY_TO } else { $null }
$resolvedRatingsDiffUseSlotThresholds = if ($RatingsDiffUseSlotThresholds) { $RatingsDiffUseSlotThresholds } elseif ($localConfig.ContainsKey("ratings_diff_use_slot_thresholds")) { [string]$localConfig["ratings_diff_use_slot_thresholds"] } elseif ($env:RATINGS_MATRIX_DIFF_USE_SLOT_THRESHOLDS) { $env:RATINGS_MATRIX_DIFF_USE_SLOT_THRESHOLDS } else { $null }
$resolvedRatingsDiffThreshold = if ($RatingsDiffThresholdPercent -ge 0) { $RatingsDiffThresholdPercent } elseif ($localConfig.ContainsKey("ratings_diff_threshold_percent")) { [double]$localConfig["ratings_diff_threshold_percent"] } elseif ($env:RATINGS_MATRIX_DIFF_THRESHOLD_PERCENT) { [double]$env:RATINGS_MATRIX_DIFF_THRESHOLD_PERCENT } else { $null }
$resolvedRatingsDiffThresholdOneSlot = if ($RatingsDiffThresholdOneSlotPercent -ge 0) { $RatingsDiffThresholdOneSlotPercent } elseif ($localConfig.ContainsKey("ratings_diff_threshold_one_slot_percent")) { [double]$localConfig["ratings_diff_threshold_one_slot_percent"] } elseif ($env:RATINGS_MATRIX_DIFF_THRESHOLD_ONE_SLOT_PERCENT) { [double]$env:RATINGS_MATRIX_DIFF_THRESHOLD_ONE_SLOT_PERCENT } else { $null }
$resolvedRatingsDiffThresholdTwoSlot = if ($RatingsDiffThresholdTwoSlotPercent -ge 0) { $RatingsDiffThresholdTwoSlotPercent } elseif ($localConfig.ContainsKey("ratings_diff_threshold_two_slot_percent")) { [double]$localConfig["ratings_diff_threshold_two_slot_percent"] } elseif ($env:RATINGS_MATRIX_DIFF_THRESHOLD_TWO_SLOT_PERCENT) { [double]$env:RATINGS_MATRIX_DIFF_THRESHOLD_TWO_SLOT_PERCENT } else { $null }
$resolvedRatingsDiffThresholdThreeSlot = if ($RatingsDiffThresholdThreeSlotPercent -ge 0) { $RatingsDiffThresholdThreeSlotPercent } elseif ($localConfig.ContainsKey("ratings_diff_threshold_three_slot_percent")) { [double]$localConfig["ratings_diff_threshold_three_slot_percent"] } elseif ($env:RATINGS_MATRIX_DIFF_THRESHOLD_THREE_SLOT_PERCENT) { [double]$env:RATINGS_MATRIX_DIFF_THRESHOLD_THREE_SLOT_PERCENT } else { $null }
$resolvedRatingsExecutionMode = if ($RatingsExecutionMode) { $RatingsExecutionMode } elseif ($localConfig.ContainsKey("ratings_execution_mode")) { $localConfig["ratings_execution_mode"] } elseif ($env:RATINGS_MATRIX_EXECUTION_MODE) { $env:RATINGS_MATRIX_EXECUTION_MODE } else { $null }
$resolvedRatingsChunkSize = if ($RatingsChunkSize -ge 0) { $RatingsChunkSize } elseif ($localConfig.ContainsKey("ratings_chunk_size")) { [int]$localConfig["ratings_chunk_size"] } elseif ($env:RATINGS_MATRIX_CHUNK_SIZE) { [int]$env:RATINGS_MATRIX_CHUNK_SIZE } else { $null }
$resolvedRatingsShowLayerReadyTimeoutMs = if ($RatingsShowLayerReadyTimeoutMs -ge 0) { $RatingsShowLayerReadyTimeoutMs } elseif ($localConfig.ContainsKey("ratings_show_layer_ready_timeout_ms")) { [int]$localConfig["ratings_show_layer_ready_timeout_ms"] } elseif ($env:RATINGS_SHOW_LAYER_READY_TIMEOUT_MS) { [int]$env:RATINGS_SHOW_LAYER_READY_TIMEOUT_MS } else { $null }
$resolvedRatingsShowLibraryLoadTimeoutMs = if ($RatingsShowLibraryLoadTimeoutMs -ge 0) { $RatingsShowLibraryLoadTimeoutMs } elseif ($localConfig.ContainsKey("ratings_show_library_load_timeout_ms")) { [int]$localConfig["ratings_show_library_load_timeout_ms"] } elseif ($env:RATINGS_SHOW_LIBRARY_LOAD_TIMEOUT_MS) { [int]$env:RATINGS_SHOW_LIBRARY_LOAD_TIMEOUT_MS } else { $null }
$resolvedRatingsLibraryLoadRetries = if ($RatingsLibraryLoadRetries -ge 0) { $RatingsLibraryLoadRetries } elseif ($localConfig.ContainsKey("ratings_library_load_retries")) { [int]$localConfig["ratings_library_load_retries"] } elseif ($env:RATINGS_LIBRARY_LOAD_RETRIES) { [int]$env:RATINGS_LIBRARY_LOAD_RETRIES } else { $null }
$resolvedRatingsRandomCount = if ($RatingsRandomCount -ge 0) { $RatingsRandomCount } elseif ($localConfig.ContainsKey("ratings_random_count")) { [int]$localConfig["ratings_random_count"] } elseif ($env:RATINGS_MATRIX_RANDOM_COUNT) { [int]$env:RATINGS_MATRIX_RANDOM_COUNT } else { $null }
$resolvedRatingsRandomSeed = if ($RatingsRandomSeed) { $RatingsRandomSeed } elseif ($localConfig.ContainsKey("ratings_random_seed")) { $localConfig["ratings_random_seed"] } elseif ($env:RATINGS_MATRIX_RANDOM_SEED) { $env:RATINGS_MATRIX_RANDOM_SEED } else { $null }
$resolvedRatingsCaseOffset = if ($RatingsCaseOffset -ge 0) { $RatingsCaseOffset } elseif ($localConfig.ContainsKey("ratings_case_offset")) { [int]$localConfig["ratings_case_offset"] } elseif ($env:RATINGS_MATRIX_CASE_OFFSET) { [int]$env:RATINGS_MATRIX_CASE_OFFSET } else { $null }
$resolvedRatingsCaseLimit = if ($RatingsCaseLimit -ge 0) { $RatingsCaseLimit } elseif ($localConfig.ContainsKey("ratings_case_limit")) { [int]$localConfig["ratings_case_limit"] } elseif ($env:RATINGS_MATRIX_CASE_LIMIT) { [int]$env:RATINGS_MATRIX_CASE_LIMIT } else { $null }
$resolvedRatingsCaseIds = if ($RatingsCaseIds) { $RatingsCaseIds } elseif ($localConfig.ContainsKey("ratings_case_ids")) { [string]$localConfig["ratings_case_ids"] } elseif ($env:RATINGS_MATRIX_CASE_IDS) { $env:RATINGS_MATRIX_CASE_IDS } else { $null }
$resolvedRatingsCaseIdsFile = if ($RatingsCaseIdsFile) { $RatingsCaseIdsFile } elseif ($localConfig.ContainsKey("ratings_case_ids_file")) { [string]$localConfig["ratings_case_ids_file"] } elseif ($env:RATINGS_MATRIX_CASE_IDS_FILE) { $env:RATINGS_MATRIX_CASE_IDS_FILE } else { $null }

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
if ($null -ne $resolvedRatingsCaseIds -and "$resolvedRatingsCaseIds".Trim() -ne "") {
  $env:RATINGS_MATRIX_CASE_IDS = [string]$resolvedRatingsCaseIds
} else {
  Remove-Item Env:RATINGS_MATRIX_CASE_IDS -ErrorAction SilentlyContinue
}
if ($null -ne $resolvedRatingsCaseIdsFile -and "$resolvedRatingsCaseIdsFile".Trim() -ne "") {
  $env:RATINGS_MATRIX_CASE_IDS_FILE = [string]$resolvedRatingsCaseIdsFile
} else {
  Remove-Item Env:RATINGS_MATRIX_CASE_IDS_FILE -ErrorAction SilentlyContinue
}
if ($null -ne $resolvedRatingsWithKometa -and "$resolvedRatingsWithKometa".Trim() -ne "") {
  $env:RATINGS_MATRIX_WITH_KOMETA = [string]$resolvedRatingsWithKometa
}
if ($null -ne $resolvedRatingsFailOnDiff -and "$resolvedRatingsFailOnDiff".Trim() -ne "") {
  $env:RATINGS_MATRIX_FAIL_ON_DIFF = [string]$resolvedRatingsFailOnDiff
}
if ($null -ne $resolvedRatingsDiffIgnoreAlpha -and "$resolvedRatingsDiffIgnoreAlpha".Trim() -ne "") {
  $env:RATINGS_MATRIX_DIFF_IGNORE_ALPHA = [string]$resolvedRatingsDiffIgnoreAlpha
}
if ($null -ne $resolvedRatingsIncludeNudges -and "$resolvedRatingsIncludeNudges".Trim() -ne "") {
  $env:RATINGS_MATRIX_INCLUDE_NUDGES = [string]$resolvedRatingsIncludeNudges
}
if ($null -ne $resolvedRatingsNudgeProfiles -and "$resolvedRatingsNudgeProfiles".Trim() -ne "") {
  $env:RATINGS_MATRIX_NUDGE_PROFILES = [string]$resolvedRatingsNudgeProfiles
}
if ($null -ne $resolvedRatingsNudgeApplyTo -and "$resolvedRatingsNudgeApplyTo".Trim() -ne "") {
  $env:RATINGS_MATRIX_NUDGE_APPLY_TO = [string]$resolvedRatingsNudgeApplyTo
}
if ($null -ne $resolvedRatingsDiffUseSlotThresholds -and "$resolvedRatingsDiffUseSlotThresholds".Trim() -ne "") {
  $env:RATINGS_MATRIX_DIFF_USE_SLOT_THRESHOLDS = [string]$resolvedRatingsDiffUseSlotThresholds
}
if ($null -ne $resolvedRatingsDiffThreshold) {
  $env:RATINGS_MATRIX_DIFF_THRESHOLD_PERCENT = [string]$resolvedRatingsDiffThreshold
}
if ($null -ne $resolvedRatingsDiffThresholdOneSlot) {
  $env:RATINGS_MATRIX_DIFF_THRESHOLD_ONE_SLOT_PERCENT = [string]$resolvedRatingsDiffThresholdOneSlot
}
if ($null -ne $resolvedRatingsDiffThresholdTwoSlot) {
  $env:RATINGS_MATRIX_DIFF_THRESHOLD_TWO_SLOT_PERCENT = [string]$resolvedRatingsDiffThresholdTwoSlot
}
if ($null -ne $resolvedRatingsDiffThresholdThreeSlot) {
  $env:RATINGS_MATRIX_DIFF_THRESHOLD_THREE_SLOT_PERCENT = [string]$resolvedRatingsDiffThresholdThreeSlot
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
if ($null -ne $resolvedRatingsLibraryLoadRetries) {
  $env:RATINGS_LIBRARY_LOAD_RETRIES = [string]$resolvedRatingsLibraryLoadRetries
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
  Write-Host "RatingsArtifacts effective config:" -ForegroundColor Cyan
  Write-Host "  profile_order=$env:RATINGS_MATRIX_PROFILE_ORDER"
  Write-Host "  execution_mode=$env:RATINGS_MATRIX_EXECUTION_MODE chunk_size=$env:RATINGS_MATRIX_CHUNK_SIZE"
  Write-Host "  random_count=$env:RATINGS_MATRIX_RANDOM_COUNT random_seed=$env:RATINGS_MATRIX_RANDOM_SEED"
  Write-Host "  case_offset=$env:RATINGS_MATRIX_CASE_OFFSET case_limit=$env:RATINGS_MATRIX_CASE_LIMIT"
  Write-Host "  case_ids=$env:RATINGS_MATRIX_CASE_IDS case_ids_file=$env:RATINGS_MATRIX_CASE_IDS_FILE"
  Write-Host "  with_kometa=$env:RATINGS_MATRIX_WITH_KOMETA fail_on_diff=$env:RATINGS_MATRIX_FAIL_ON_DIFF diff_ignore_alpha=$env:RATINGS_MATRIX_DIFF_IGNORE_ALPHA"
  Write-Host "  include_nudges=$env:RATINGS_MATRIX_INCLUDE_NUDGES nudge_profiles=$env:RATINGS_MATRIX_NUDGE_PROFILES nudge_apply_to=$env:RATINGS_MATRIX_NUDGE_APPLY_TO"
  Write-Host "  diff_use_slot_thresholds=$env:RATINGS_MATRIX_DIFF_USE_SLOT_THRESHOLDS diff_threshold_percent=$env:RATINGS_MATRIX_DIFF_THRESHOLD_PERCENT"
  Write-Host "  slot_thresholds(one/two/three)=$env:RATINGS_MATRIX_DIFF_THRESHOLD_ONE_SLOT_PERCENT/$env:RATINGS_MATRIX_DIFF_THRESHOLD_TWO_SLOT_PERCENT/$env:RATINGS_MATRIX_DIFF_THRESHOLD_THREE_SLOT_PERCENT"
  Write-Host "  show_layer_ready_timeout_ms=$env:RATINGS_SHOW_LAYER_READY_TIMEOUT_MS show_library_load_timeout_ms=$env:RATINGS_SHOW_LIBRARY_LOAD_TIMEOUT_MS library_load_retries=$env:RATINGS_LIBRARY_LOAD_RETRIES"
  Write-Host "  movie_library=$env:RATINGS_MATRIX_MOVIE_LIBRARY show_library=$env:RATINGS_MATRIX_SHOW_LIBRARY artifact_dir=$env:RATINGS_MATRIX_ARTIFACT_DIR"
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
