# Experiment E2 results: read-only. Collects diagnostics, checks the validation
# records against the newest save file, asks three yes/no questions and zips it all.
param([string]$Save = '')
. (Join-Path $PSScriptRoot 'common.ps1')

$out = Join-Path $ResultsDir 'e2'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$log = Start-Log $out 'check_log.txt'
$Save = ConvertTo-CleanPath $Save
$py = Require-Python
if (-not $py) { Stop-Log; exit 1 }
$userDir = Get-SimsUserDir
if (Test-GameRunning) { Write-Warn2 'The game is still running: quit it so the newest save is on disk, then rerun.' }

Write-Step 'Your observations (press Enter to skip a question)'
$q = @('Right after the first facescan.step, did the Sim''s face visibly change? (y/n)',
       'In Modify in CAS, did the face look changed too? (y/n)',
       'After reloading the save, did the Sim still have the changed face? (y/n)',
       'Anything else you noticed (error messages, crashes)?')
$notes = @()
foreach ($question in $q) {
    $answer = if ($env:FACESCAN_ASSUME_YES) { '(skipped)' } else { Read-Host $question }
    $notes += ($question + ' -> ' + $answer)
}
$notesPath = Join-Path $out 'my_notes.txt'
$notes | Set-Content -Path $notesPath -Encoding UTF8

Write-Step 'Diagnostics'
Invoke-Diagnostics $py 'e2-check' (Join-Path $out 'diagnostics')

Write-Step 'Validation records vs the newest save file'
$argsE2 = @((Join-Path $RepoRoot 'tools\check_validation.py'), '--user-dir', $userDir)
if ($Save) { $argsE2 += @('--save', $Save) }
$code = Invoke-Python $py $argsE2

Stop-Log
$fs = Join-Path $userDir 'facescan'
$zip = Join-Path (Get-DesktopPath) 'facescan_e2_results.zip'
Save-ResultsZip @((Join-Path $out 'diagnostics'), (Join-Path $out 'install_diagnostics'),
                  (Join-Path $out 'install_log.txt'), $log, $notesPath,
                  (Join-Path $fs 'validation'), (Join-Path $fs 'out')) $zip
if ($code -eq 0) { Write-Ok 'All checkpoints PASSED (including the save file on disk).' }
else { Write-Warn2 'Not everything passed or the test is incomplete; the zip contains the details.' }
Write-Host 'Send facescan_e2_results.zip back.'
exit $code
