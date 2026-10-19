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
    $cands = @(@('py', '-3.7'), @('C:\Python37\python.exe'), @('C:\Program Files\Python37\python.exe'))
    if ($env:LOCALAPPDATA) { $cands += , @(Join-Path $env:LOCALAPPDATA 'Programs\Python\Python37\python.exe') }
    foreach ($cand in $cands) {
        $v = Get-PythonVersion $cand
        if ($v -and $v.Major -eq 3 -and $v.Minor -eq 7) { return , $cand }
    }
    return $null
}

function Invoke-Python([string[]]$Py, [string[]]$ScriptArgs) {
    $exe = $Py[0]
    $rest = @()
    if ($Py.Count -gt 1) { $rest = $Py[1..($Py.Count - 1)] }
    & $exe @rest @ScriptArgs | Out-Host   # show output; keep it out of the return value
    return $LASTEXITCODE
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
function Get-SimsUserDir {
    $docs = [Environment]::GetFolderPath('MyDocuments')
    return (Join-Path $docs 'Electronic Arts\The Sims 4')
}

function Test-GameRunning {
    return [bool](Get-Process -Name 'TS4_x64', 'TS4_DX9_x64', 'TS4' -ErrorAction SilentlyContinue)
}

function Confirm-Yes([string]$Question, [bool]$DefaultYes = $true) {
    $suffix = if ($DefaultYes) { '[Y/n]' } else { '[y/N]' }
    $a = Read-Host "$Question $suffix"
    if ([string]::IsNullOrWhiteSpace($a)) { return $DefaultYes }
    return $a.Trim().ToLower().StartsWith('y')
}

function Get-DesktopPath { return [Environment]::GetFolderPath('Desktop') }
