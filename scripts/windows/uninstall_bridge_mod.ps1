# Removes the FaceScan bridge mod from the Mods folder. Leaves results and backups alone.
. (Join-Path $PSScriptRoot 'common.ps1')

$mod = Join-Path (Get-SimsUserDir) 'Mods\facescan_bridge.ts4script'
if (Test-GameRunning) { Write-Warn2 'Quit the game first.'; exit 1 }
if (Test-Path $mod) {
    Remove-Item $mod
    Write-Ok "Removed $mod"
} else {
    Write-Ok 'The mod is not installed.'
}
Write-Host ('Test data stays in ' + (Join-Path (Get-SimsUserDir) 'facescan') + ' (safe to delete).')
