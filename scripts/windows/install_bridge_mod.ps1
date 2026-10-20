# Experiment E2 setup: back up saves, install the test mod, archive old test data.
# Asks before changing anything. Reverse with E2_uninstall_mod.bat.
#   -Method auto       (default) packaged .ts4script if Python 3.7 is installed, else loose scripts
#   -Method ts4script  Mods\facescan_bridge.ts4script (compiled with Python 3.7, standard for released mods)
#   -Method scripts    Mods\FaceScanBridge\Scripts\facescan_bridge.py (no Python 3.7 needed)
param([ValidateSet('auto', 'ts4script', 'scripts')][string]$Method = 'auto')
. (Join-Path $PSScriptRoot 'common.ps1')

$out = Join-Path $ResultsDir 'e2'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$log = Start-Log $out 'install_log.txt'
$userDir = Get-SimsUserDir
$modsDir = Join-Path $userDir 'Mods'
Write-Host "Sims 4 user folder: $userDir"
$py = Find-Python
if (-not $py) { Write-Warn2 'Python 3.9+ not found; run E1_inventory.bat first (it explains how to install it).'; Stop-Log; exit 1 }
if (-not (Test-Path $userDir)) { Write-Warn2 'Folder not found. Start the game once, then rerun.'; Stop-Log; exit 1 }
if (Test-GameRunning) { Write-Warn2 'The Sims 4 is running. Please quit the game first, then rerun.'; Stop-Log; exit 1 }

Write-Step '1. Back up saves'
$saves = Join-Path $userDir 'saves'
if ((Test-Path $saves) -and (Confirm-Yes 'Create a zip backup of your saves folder first? (strongly recommended)')) {
    $bdir = Join-Path (Split-Path (Split-Path $userDir)) 'FaceScan_backups'   # Documents\FaceScan_backups
    New-Item -ItemType Directory -Force -Path $bdir | Out-Null
    $bzip = Join-Path $bdir ('saves_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.zip')
    Compress-Archive -Path (Join-Path $saves '*') -DestinationPath $bzip
    Write-Ok "Backup: $bzip"
}

Write-Step '2. Choose install method'
$py37 = Find-Python37
if ($Method -eq 'auto') { $Method = if ($py37) { 'ts4script' } else { 'scripts' } }
if ($Method -eq 'ts4script' -and -not $py37) {
    Write-Warn2 'The ts4script method needs Python 3.7: winget install -e --id Python.Python.3.7'
    Write-Host  'Or rerun with the default method (no Python 3.7 needed).'
    Stop-Log; exit 1
}
Write-Ok "Method: $Method"
if (-not (Confirm-Yes "Install the FaceScan test mod into $modsDir ?")) { Stop-Log; exit 0 }

Write-Step '3. Remove any previous FaceScan install and archive old test data'
$packed = Join-Path $modsDir 'facescan_bridge.ts4script'
$looseDir = Join-Path $modsDir 'FaceScanBridge'
if (Test-Path $packed) { Remove-Item $packed -Force; Write-Ok 'Removed old facescan_bridge.ts4script' }
if (Test-Path $looseDir) { Remove-Item $looseDir -Recurse -Force; Write-Ok 'Removed old FaceScanBridge folder' }
$fs = Join-Path $userDir 'facescan'
if (Test-Path $fs) {
    $arch = Join-Path $fs ('archive\' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
    New-Item -ItemType Directory -Force -Path $arch | Out-Null
    foreach ($item in @('mod_loaded.json', 'facescan_log.txt', 'validation', 'out')) {
        $p = Join-Path $fs $item
        if (Test-Path $p) { Move-Item $p $arch }
    }
    Write-Ok "Previous test data archived to $arch"
}

Write-Step '4. Install'
New-Item -ItemType Directory -Force -Path $modsDir | Out-Null
$source = Join-Path $RepoRoot 'mod\facescan_bridge\facescan_bridge.py'
if ($Method -eq 'ts4script') {
    $code = Invoke-Python $py37 @((Join-Path $RepoRoot 'mod\build.py'))
    if ($code -ne 0) { Write-Warn2 'Build failed; see the messages above.'; Stop-Log; exit $code }
    Copy-Item (Join-Path $RepoRoot 'mod\dist\facescan_bridge.ts4script') $packed -Force
    Write-Ok "Installed $packed"
} else {
    $target = Join-Path $looseDir 'Scripts'
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item $source (Join-Path $target 'facescan_bridge.py') -Force
    Write-Ok "Installed $(Join-Path $target 'facescan_bridge.py')"
}

Write-Step '5. Check settings'
Invoke-Diagnostics $py 'e2-install' (Join-Path $out 'install_diagnostics')
Stop-Log
Write-Host ''
Write-Host 'NEXT (in the game):' -ForegroundColor Cyan
Write-Host ' 1. Options > Game Options > Other: tick "Enable Custom Content and Mods" and "Script Mods Allowed". Restart the game.'
Write-Host ' 2. New Game > create a Young Adult with LAST NAME FaceScanTest > play > save under a new name.'
Write-Host ' 3. Press Ctrl+Shift+C and type:  facescan.step   (repeat it; it tells you each next action)'
Write-Host ' 4. When it says TEST COMPLETE: quit the game and double-click E2_check_results.bat'
