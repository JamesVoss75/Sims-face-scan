# Experiment E2 setup: back up saves, build the bridge mod with Python 3.7,
# and copy it into the Mods folder. Asks before every change.
. (Join-Path $PSScriptRoot 'common.ps1')

$userDir = Get-SimsUserDir
$modsDir = Join-Path $userDir 'Mods'
Write-Host "Sims 4 user folder: $userDir"
if (-not (Test-Path $userDir)) { Write-Warn2 'Folder not found. Start the game once, then rerun.'; exit 1 }
if (Test-GameRunning) { Write-Warn2 'The Sims 4 is running. Please quit the game first.'; exit 1 }

Write-Step '1. Back up saves'
$saves = Join-Path $userDir 'saves'
if (Test-Path $saves) {
    if (Confirm-Yes 'Create a zip backup of your saves folder first? (strongly recommended)') {
        $bdir = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'FaceScan_backups'
        New-Item -ItemType Directory -Force -Path $bdir | Out-Null
        $bzip = Join-Path $bdir ("saves_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.zip')
        Compress-Archive -Path (Join-Path $saves '*') -DestinationPath $bzip
        Write-Ok "Backup: $bzip"
    }
}

Write-Step '2. Build the mod with Python 3.7 (the game embeds Python 3.7)'
$py37 = Find-Python37
if (-not $py37) {
    Write-Warn2 'Python 3.7 was not found.'
    if ((Get-Command winget -ErrorAction SilentlyContinue) -and (Confirm-Yes 'Install Python 3.7 with winget now?')) {
        winget install -e --id Python.Python.3.7
        $py37 = Find-Python37
    }
    if (-not $py37) {
        Write-Host 'Install Python 3.7.9 from https://www.python.org/downloads/release/python-379/'
        Write-Host '("Windows x86-64 executable installer"), then rerun this script.'
        exit 1
    }
}
$code = Invoke-Python $py37 @((Join-Path $RepoRoot 'mod\build.py'))
if ($code -ne 0) { Write-Warn2 'Build failed.'; exit $code }
$built = Join-Path $RepoRoot 'mod\dist\facescan_bridge.ts4script'

Write-Step '3. Install into Mods'
if (-not (Confirm-Yes "Copy facescan_bridge.ts4script into $modsDir ?")) { exit 0 }
New-Item -ItemType Directory -Force -Path $modsDir | Out-Null
Copy-Item $built (Join-Path $modsDir 'facescan_bridge.ts4script') -Force
Write-Ok 'Installed'

Write-Step '4. Script mod setting'
$ini = Join-Path $userDir 'Options.ini'
if (Test-Path $ini) {
    $text = Get-Content $ini -Raw
    if ($text -match '(?im)^\s*scriptmodsenabled\s*=\s*1') { Write-Ok 'Options.ini: script mods enabled' }
    else { Write-Warn2 'Could not confirm script mods are enabled. In the game: Options > Game Options > Other > enable "Custom Content and Mods" and "Script Mods Allowed", then restart the game.' }
} else {
    Write-Warn2 'Options.ini not found; enable script mods in the game options (see above).'
}
Write-Host ''
Write-Host 'Next: follow docs\windows-testing.md, section "Experiment 2".'
