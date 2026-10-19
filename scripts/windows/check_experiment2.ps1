# Experiment E2 analysis: read-only. Checks the validation records written by the
# mod and the newest save file, then zips everything for sending back.
param([string]$Save = '')
. (Join-Path $PSScriptRoot 'common.ps1')

$py = Require-Python
$userDir = Get-SimsUserDir
$argsE2 = @((Join-Path $RepoRoot 'tools\check_validation.py'), '--user-dir', $userDir)
if ($Save) { $argsE2 += @('--save', $Save) }
if (Test-GameRunning) { Write-Warn2 'The game is running: the newest save on disk may be older than what you see in game.' }
$code = Invoke-Python $py $argsE2

$fs = Join-Path $userDir 'facescan'
$items = @((Join-Path $fs 'validation'), (Join-Path $fs 'out')) | Where-Object { Test-Path $_ }
$exc = Get-ChildItem -Path $userDir -Filter 'lastException*.txt' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 3
$all = @($items) + @($exc | ForEach-Object { $_.FullName })
if ($all.Count -gt 0) {
    $zip = Join-Path (Get-DesktopPath) 'facescan_e2_results.zip'
    Compress-Archive -Path $all -DestinationPath $zip -Force
    Write-Ok "Results: $zip  (send this back)"
}
if ($code -eq 0) { Write-Ok 'All required checkpoints PASSED' } else { Write-Warn2 'Some checks did not pass or are missing; see the report above.' }
exit $code
