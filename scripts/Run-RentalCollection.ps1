param(
    [string]$BoundaryPath,
    [string]$OutputDirectory,
    [string]$SanggaSnapshotPath,
    [string]$DdakCheckpointPath,
    [string]$HeybdCheckpointPath,
    [switch]$SanggaOnly
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$collector = Join-Path $PSScriptRoot 'collect_rentals.py'
$collectorArgs = @('"' + $collector + '"')
if ($BoundaryPath) {
    $collectorArgs += '--boundary', ('"' + (Resolve-Path -LiteralPath $BoundaryPath).Path + '"')
}
$directory = if ($OutputDirectory) {
    $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory)
} else {
    Join-Path $project 'data/rental_collection'
}
$collectorArgs += '--output', ('"' + $directory + '"')
if ($SanggaSnapshotPath) {
    $collectorArgs += '--sangga-snapshot', ('"' + (Resolve-Path -LiteralPath $SanggaSnapshotPath).Path + '"')
}
if (-not $SanggaOnly) {
    $today = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTimeOffset]::UtcNow, 'Korea Standard Time').ToString('yyyyMMdd')
    $marketCollector = Join-Path $PSScriptRoot 'collect_market_rentals.mjs'
    $checkpoints = @{
        ddak = $DdakCheckpointPath
        heybd = $HeybdCheckpointPath
    }
    foreach ($source in @('ddak', 'heybd')) {
        $checkpoint = if ($checkpoints[$source]) {
            $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($checkpoints[$source])
        } else {
            Join-Path $directory "$source-$today"
        }
        & node $marketCollector $checkpoint $source
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        $collectorArgs += '--market-checkpoint', $source, ('"' + $checkpoint + '"')
    }
}

$process = Start-Process -FilePath 'C:\Program Files\Python313\python.exe' `
    -ArgumentList $collectorArgs -WorkingDirectory $project -Wait -PassThru -NoNewWindow
exit $process.ExitCode
