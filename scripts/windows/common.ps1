# Shared helpers for the FaceScan Windows test scripts. Dot-source this file.
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ResultsDir = Join-Path $RepoRoot 'results'

function Write-Step([string]$Text) { Write-Host ''; Write-Host "== $Text" -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host "OK  $Text" -ForegroundColor Green }
function Write-Warn2([string]$Text) { Write-Host "!!  $Text" -ForegroundColor Yellow }

function Get-PythonVersion([string[]]$Cmd) {
    try {
        $exe = $Cmd[0]
        $rest = @()
        if ($Cmd.Count -gt 1) { $rest = $Cmd[1..($Cmd.Count - 1)] }
        $v = & $exe @rest -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>$null
        if ($LASTEXITCODE -eq 0 -and $v) { return [version]($v.Trim()) }
    } catch { }
    return $null
}

# Returns a command array (e.g. @('py','-3')) for a Python >= 3.9, or $null.
function Find-Python {
    foreach ($cand in @(@('py', '-3'), @('python'), @('python3'))) {
        $v = Get-PythonVersion $cand
        if ($v -and $v -ge [version]'3.9') { return , $cand }
    }
    return $null
}

# Returns a command array for Python 3.7 exactly (needed only to build the mod), or $null.
function Find-Python37 {
    if ($env:FACESCAN_PY37) { return , @($env:FACESCAN_PY37) }   # explicit override
    $cands = @(@('py', '-3.7'), @('C:\Python37\python.exe'), @('C:\Program Files\Python37\python.exe'))
    if ($env:LOCALAPPDATA) { $cands += , @(Join-Path $env:LOCALAPPDATA 'Programs\Python\Python37\python.exe') }
    foreach ($cand in $cands) {
        $v = Get-PythonVersion $cand
        if ($v -and $v.Major -eq 3 -and $v.Minor -eq 7) { return , $cand }
    }
    return $null
}

# Python prints UTF-8 regardless of the console code page (user names with accents).
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

function Invoke-Python([string[]]$Py, [string[]]$ScriptArgs) {
    $exe = $Py[0]
    $rest = @()
    if ($Py.Count -gt 1) { $rest = $Py[1..($Py.Count - 1)] }
    # Merge stderr (tracebacks) into the visible, transcribed output. Windows PowerShell 5.1
    # turns redirected stderr into errors, which must not abort the script.
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $exe @rest @ScriptArgs 2>&1 | ForEach-Object { "$_" } | Out-Host
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $old
    }
    return $code
}

function Require-Python {
    $py = Find-Python
    if (-not $py) {
        Write-Warn2 'Python 3.9 or newer was not found.'
        Write-Host  'Install it from https://www.python.org/downloads/ (tick "Add python.exe to PATH"),'
        Write-Host  'or run:  winget install -e --id Python.Python.3.12'
        Write-Host  'Then run this script again.'
        exit 1
    }
    return , $py
}

# Documents\Electronic Arts\The Sims 4 (follows OneDrive folder redirection).
# Override with $env:FACESCAN_USER_DIR if detection is wrong.
function Get-SimsUserDir {
    if ($env:FACESCAN_USER_DIR) { return $env:FACESCAN_USER_DIR }
    $docs = [Environment]::GetFolderPath('MyDocuments')
    return (Join-Path $docs 'Electronic Arts\The Sims 4')
}

function Test-GameRunning {
    return [bool](Get-Process -Name 'TS4_x64', 'TS4_DX9_x64', 'TS4' -ErrorAction SilentlyContinue)
}

function Confirm-Yes([string]$Question, [bool]$DefaultYes = $true) {
    if ($env:FACESCAN_ASSUME_YES) { Write-Host "$Question (auto: yes)"; return $true }
    $suffix = if ($DefaultYes) { '[Y/n]' } else { '[y/N]' }
    $a = Read-Host "$Question $suffix"
    if ([string]::IsNullOrWhiteSpace($a)) { return $DefaultYes }
    return $a.Trim().ToLower().StartsWith('y')
}

function Get-DesktopPath {
    if ($env:FACESCAN_DESKTOP) { return $env:FACESCAN_DESKTOP }
    return [Environment]::GetFolderPath('Desktop')
}

# Console transcript for troubleshooting (included in the results zip).
function Start-Log([string]$Dir, [string]$Name) {
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    $path = Join-Path $Dir $Name
    try { Start-Transcript -Path $path -Force | Out-Null } catch { }
    Write-Host ("FaceScan " + (Split-Path -Leaf $MyInvocation.PSCommandPath) + " started " + (Get-Date -Format s))
    Write-Host ("Windows: " + [Environment]::OSVersion.VersionString + "; PowerShell " + $PSVersionTable.PSVersion)
    return $path
}

function Stop-Log { try { Stop-Transcript | Out-Null } catch { } }

# Runs tools/collect_diagnostics.py; never fails the calling script.
function Invoke-Diagnostics([string[]]$Py, [string]$Stage, [string]$OutDir, [string]$GameDir = '') {
    $a = @((Join-Path $RepoRoot 'tools\collect_diagnostics.py'), '--stage', $Stage, '--out', $OutDir,
           '--user-dir', (Get-SimsUserDir))
    if ($GameDir) { $a += @('--game-dir', $GameDir) }
    try { $null = Invoke-Python $Py $a } catch { Write-Warn2 "Diagnostics collector failed: $_" }
}

# Zip whatever of $Paths exists into $Zip (on the Desktop), replacing an old zip.
function Save-ResultsZip([string[]]$Paths, [string]$Zip) {
    $existing = @($Paths | Where-Object { $_ -and (Test-Path $_) })
    if ($existing.Count -eq 0) { Write-Warn2 'Nothing to package.'; return }
    if (Test-Path $Zip) { Remove-Item $Zip -Force }
    Compress-Archive -Path $existing -DestinationPath $Zip -Force
    Write-Ok "Results: $Zip"
}
