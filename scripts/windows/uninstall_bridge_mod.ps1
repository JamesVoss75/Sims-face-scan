# Removes the FaceScan test mod (both install methods). Leaves results, backups and saves alone.
# To also put the test Sim's original face back, run facescan.undo in the game BEFORE uninstalling.
. (Join-Path $PSScriptRoot 'common.ps1')

$mods = Join-Path (Get-SimsUserDir) 'Mods'
if (Test-GameRunning) { Write-Warn2 'Quit the game first.'; exit 1 }
$removed = $false
foreach ($p in @((Join-Path $mods 'facescan_bridge.ts4script'), (Join-Path $mods 'FaceScanBridge'))) {
    if (Test-Path $p) { Remove-Item $p -Recurse -Force; Write-Ok "Removed $p"; $removed = $true }
}
if (-not $removed) { Write-Ok 'The mod is not installed.' }
Write-Host ('Test data stays in ' + (Join-Path (Get-SimsUserDir) 'facescan') + ' (safe to delete).')
Write-Host 'Save backups (if made) are in Documents\FaceScan_backups.'
