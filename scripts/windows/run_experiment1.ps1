# Experiment E1 (+ E1b): read-only inventory of the game's face data, a codec check
# against your existing saves, and an environment report. Changes nothing in the
# game folder or the saves.
param([string]$GameDir = '')
. (Join-Path $PSScriptRoot 'common.ps1')

$out = Join-Path $ResultsDir 'e1'
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
$log = Start-Log $out 'console_log.txt'
Write-Host 'FaceScan Experiment 1 - read-only. Nothing in the game folder or your saves is modified.'
$py = Find-Python
if (-not $py) {
    Write-Warn2 'Python 3.9 or newer was not found.'
    Write-Host  'Install it with:  winget install -e --id Python.Python.3.12'
    Write-Host  'or from https://www.python.org/downloads/ (tick "Add python.exe to PATH"), then run this again.'
    Stop-Log; exit 1
}
Write-Ok ("Python: " + ($py -join ' '))

Write-Step 'Environment report (game version, packs, settings)'
Invoke-Diagnostics $py 'e1' (Join-Path $out 'diagnostics') $GameDir

Write-Step 'E1: scanning game packages (takes a few minutes)'
$inv = Join-Path $RepoRoot 'tools\inventory_game_files.py'
$argsE1 = @($inv)
if ($GameDir) { $argsE1 += $GameDir }
$argsE1 += @('--out', $out)
$code = Invoke-Python $py $argsE1
if ($code -eq 1 -and -not $GameDir) {
    Write-Warn2 'The game folder was not found automatically.'
    $GameDir = Read-Host 'Paste the Sims 4 install folder (the one containing "Game" and "Data")'
    $code = Invoke-Python $py @($inv, $GameDir, '--out', $out)
    Invoke-Diagnostics $py 'e1' (Join-Path $out 'diagnostics') $GameDir
}
if ($code -ne 0) { Write-Warn2 "Inventory failed (exit $code). The results zip still contains the details." }
else { Write-Ok 'Inventory done' }

Write-Step 'E1b: checking the face-data reader against your saves (read-only)'
$saves = Join-Path (Get-SimsUserDir) 'saves'
if (Test-Path $saves) {
    $code = Invoke-Python $py @((Join-Path $RepoRoot 'tools\verify_blob_codec.py'), '--saves', $saves,
                                '--out', (Join-Path $out 'e1b_codec_report.json'))
    if ($code -ne 0) { Write-Warn2 "Codec check reported problems (exit $code); the report explains." }
} else {
    Write-Warn2 "No saves folder at $saves; skipping E1b."
}

Stop-Log
$zip = Join-Path (Get-DesktopPath) 'facescan_e1_results.zip'
Save-ResultsZip @((Join-Path $out 'summary.json'), (Join-Path $out 'catalog.json'),
                  (Join-Path $out 'e1b_codec_report.json'), (Join-Path $out 'diagnostics'), $log) $zip
Write-Host 'Send that zip back. (EA tuning files in results\e1\tuning stay on your PC.)'
