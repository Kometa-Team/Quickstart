param(
  [switch]$E2E,
  [switch]$Unit,
  [switch]$Lint,
  [switch]$RepoChecks,
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
  [switch]$Setup,
  [switch]$All
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$windowsPython = Join-Path $repoRoot "venv\\Scripts\\python.exe"
$unixPython = Join-Path $repoRoot "venv/bin/python"
$python = if (Test-Path $windowsPython) {
  $windowsPython
} elseif (Test-Path $unixPython) {
  $unixPython
} else {
  "python"
}
$runner = Join-Path $PSScriptRoot "run_tests.py"

function Convert-ToKebabCase {
  param(
    [string]$Value
  )

  return (($Value -creplace '([a-z0-9])([A-Z])', '$1-$2').ToLowerInvariant())
}

$forwardArgs = @($runner)
foreach ($entry in $PSBoundParameters.GetEnumerator()) {
  $argName = "--$(Convert-ToKebabCase -Value $entry.Key)"
  if ($entry.Value -is [System.Management.Automation.SwitchParameter]) {
    if ($entry.Value.IsPresent) {
      $forwardArgs += $argName
    }
  } elseif ($null -ne $entry.Value) {
    $forwardArgs += $argName
    $forwardArgs += [string]$entry.Value
  }
}

Push-Location $repoRoot
try {
  & $python @forwardArgs
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
