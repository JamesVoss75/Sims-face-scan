# Experiment E1 (+ E1b): read-only inventory of the game's face data and a codec
# check against your existing saves. Changes nothing in the game or the saves.
param([string]$GameDir = '')
. (Join-Path $PSScriptRoot 'common.ps1')

Write-Host 'FaceScan Experiment 1 - read-only. Nothing in the game folder or your saves is modified.'
$py = Require-Python
Write-Ok ("Python: " + ($py -join ' '))

$out = Join-Path $ResultsDir 'e1'
New-Item -ItemType Directory -Force -Path $out | Out-Null

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
}
if ($code -ne 0) { Write-Warn2 "Inventory failed (exit $code). Please send the text above."; exit $code }
Write-Ok 'Inventory done'

Write-Step 'E1b: checking the face-data codec against your saves (read-only)'
$saves = Join-Path (Get-SimsUserDir) 'saves'
$e1b = Join-Path $out 'e1b_codec_report.json'
if (Test-Path $saves) {
    $code = Invoke-Python $py @((Join-Path $RepoRoot 'tools\verify_blob_codec.py'), '--saves', $saves, '--out', $e1b)
    if ($code -ne 0) { Write-Warn2 "Codec check reported problems (exit $code); the report explains." }
} else {
    Write-Warn2 "No saves folder at $saves; skipping E1b."
}

Write-Step 'Packaging results'
$zip = Join-Path (Get-DesktopPath) 'facescan_e1_results.zip'
$files = @('summary.json', 'catalog.json', 'e1b_codec_report.json') |
    ForEach-Object { Join-Path $out $_ } | Where-Object { Test-Path $_ }
Compress-Archive -Path $files -DestinationPath $zip -Force
Write-Ok "Results: $zip"
Write-Host 'Send that zip back. (The tuning\*.xml files are EA data and stay on your PC.)'
