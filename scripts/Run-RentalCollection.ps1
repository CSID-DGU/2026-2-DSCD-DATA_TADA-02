param(
    [string]$BoundaryPath,
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$collector = Join-Path $PSScriptRoot 'collect_rentals.py'
$collectorArgs = @('"' + $collector + '"')
if ($BoundaryPath) {
    $collectorArgs += '--boundary', ('"' + (Resolve-Path -LiteralPath $BoundaryPath).Path + '"')
}
if ($OutputDirectory) {
    $directory = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory)
    $collectorArgs += '--output', ('"' + $directory + '"')
}

$process = Start-Process -FilePath 'C:\Program Files\Python313\python.exe' `
    -ArgumentList $collectorArgs -WorkingDirectory $project -Wait -PassThru -NoNewWindow
exit $process.ExitCode
