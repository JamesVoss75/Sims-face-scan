# Shared helpers for the FaceScan Windows test scripts. Dot-source this file.
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ResultsDir = Join-Path $RepoRoot 'results'

# Python writes UTF-8 and PowerShell decodes native output as UTF-8, so paths with
# non-ASCII characters (user names with accents) survive the round trip.
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch { }

function Write-Step([string]$Text) { Write-Host ''; Write-Host "== $Text" -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host "OK  $Text" -ForegroundColor Green }
function Write-Warn2([string]$Text) { Write-Host "!!  $Text" -ForegroundColor Yellow }

# ---------------------------------------------------------------------------
# Python detection
#
# Each candidate command is run on tools\python_probe.py (a file, so no quoted
# code is passed on the command line: Windows PowerShell 5.1 strips embedded
# double quotes from native-command arguments, which broke the old
# `python -c "..."` check). Every attempt is recorded with the reason it was
# accepted or rejected; Write-PythonReport prints them when detection fails.
# The command returned is the probed interpreter's own python.exe, so the
# launcher or an alias is only used to find it.
# ---------------------------------------------------------------------------
$ProbeScript = Join-Path $RepoRoot 'tools\python_probe.py'
$script:PythonAttempts = @()

function Test-PythonCandidate([string[]]$Cmd) {
    $r = [pscustomobject]@{ Command = ($Cmd -join ' '); Resolved = ''; Ok = $false; Version = $null
                            Executable = ''; Reason = ''; Output = '' }
    $exe = $Cmd[0]
    $gc = Get-Command $exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $gc) { $r.Reason = 'not found'; return $r }
    $r.Resolved = $gc.Source
    $rest = @()
    if ($Cmd.Count -gt 1) { $rest = $Cmd[1..($Cmd.Count - 1)] }
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $lines = @(& $exe @rest $ProbeScript 2>&1 | ForEach-Object { "$_" })
        $code = $LASTEXITCODE
    } catch {
        $r.Reason = 'could not start: ' + $_.Exception.Message
        return $r
    } finally {
        $ErrorActionPreference = $old
    }
    $r.Output = (($lines | Select-Object -First 6) -join ' | ')
    $line = $lines | Where-Object { $_ -like 'FACESCAN_PROBE|*' } | Select-Object -First 1
    if (-not $line) {
        if ($r.Resolved -match '\\WindowsApps\\' -or $r.Output -match 'Microsoft Store') {
            $r.Reason = "Microsoft Store alias without an installed Python (exit $code)"
        } else {
            $r.Reason = "did not run the probe (exit $code)"
        }
        return $r
    }
    $parts = $line.Split('|')
    $ver = $null
    if (-not [version]::TryParse($parts[1], [ref]$ver)) { $r.Reason = "unreadable version '$($parts[1])'"; return $r }
    $r.Version = $ver
    $r.Executable = $parts[2]
    $r.Ok = $true
    return $r
}

# Version of one candidate command (e.g. @('py','-3')), or $null. Kept for manual debugging:
#   . .\scripts\windows\common.ps1; Get-PythonVersion @('py','-3'); Test-PythonCandidate @('python')
function Get-PythonVersion([string[]]$Cmd) {
    $r = Test-PythonCandidate $Cmd
    if ($r.Ok) { return $r.Version }
    Write-Host ("{0}: {1}" -f $r.Command, $r.Reason)
    return $null
}

# Candidate commands, most preferred first: explicit override, the py launcher,
# PATH, every interpreter the launcher knows (`py -0p`), usual install folders.
function Get-PythonCandidates([string]$LauncherArg = '-3') {
    $c = New-Object System.Collections.ArrayList
    if ($env:FACESCAN_PYTHON) { [void]$c.Add(@($env:FACESCAN_PYTHON)) }
    [void]$c.Add(@('py', $LauncherArg))
    [void]$c.Add(@('python'))
    [void]$c.Add(@('python3'))
    if (Get-Command py -CommandType Application -ErrorAction SilentlyContinue) {
        $old = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try { $list = @(& py -0p 2>&1 | ForEach-Object { "$_" }) } catch { $list = @() }
        finally { $ErrorActionPreference = $old }
        foreach ($l in $list) {
            # e.g. " -V:3.12 *   C:\...\Python312\python.exe" or " -3.12-64   C:\...\python.exe *"
            $m = [regex]::Match($l, '([A-Za-z]:\\.*?\\python[w]?\.exe|/[^\s*]*python[0-9.]*)')
            if ($m.Success) { [void]$c.Add(@($m.Groups[1].Value.Trim())) }
        }
    }
    $roots = @()
    if ($env:LOCALAPPDATA) { $roots += (Join-Path $env:LOCALAPPDATA 'Programs\Python') }
    if ($env:ProgramFiles) { $roots += $env:ProgramFiles }
    $roots += 'C:\'
    foreach ($root in $roots) {
        if (Test-Path $root) {
            Get-ChildItem -Path $root -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue |
                Sort-Object Name -Descending | ForEach-Object {
                    $exe = Join-Path $_.FullName 'python.exe'
                    if (Test-Path $exe) { [void]$c.Add(@($exe)) }
                }
        }
    }
    return , $c
}

function Select-Python([scriptblock]$Accept, [string]$LauncherArg = '-3') {
    $script:PythonAttempts = @()
    $seen = @{}
    foreach ($cand in (Get-PythonCandidates $LauncherArg)) {
        $key = ($cand -join ' ').ToLower()
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        $r = Test-PythonCandidate $cand
        if ($r.Ok -and -not (& $Accept $r.Version)) { $r.Ok = $false; $r.Reason = "version $($r.Version) not accepted" }
        $script:PythonAttempts += $r
        if ($r.Ok) {
            # Use the interpreter itself from now on (works with spaces in the path).
            if ($r.Executable -and (Test-Path -LiteralPath $r.Executable)) { return , @($r.Executable) }
            return , $cand
        }
    }
    return $null
}

function Write-PythonReport([string]$Wanted) {
    Write-Host "Python detection ($Wanted) tried:"
    foreach ($a in $script:PythonAttempts) {
        $status = if ($a.Ok) { "OK  Python $($a.Version) at $($a.Executable)" } else { "no  $($a.Reason)" }
        Write-Host ("  {0,-45} {1}" -f $a.Command, $status)
        if ($a.Resolved) { Write-Host ("  {0,-45}   resolved to {1}" -f '', $a.Resolved) }
        if (-not $a.Ok -and $a.Output) { Write-Host ("  {0,-45}   output: {1}" -f '', $a.Output) }
    }
}

# Returns a command array for a working Python >= 3.9, or $null.
function Find-Python {
    $py = Select-Python { param($v) $v -ge [version]'3.9' } '-3'
    if ($py) { Write-Host ("Python found: " + ($py -join ' ') + " (" + ($script:PythonAttempts[-1].Version) + ")") }
    return $py
}

# Returns a command array for Python 3.7 exactly (needed only to build the packaged mod), or $null.
function Find-Python37 {
    $saved = $env:FACESCAN_PYTHON
    if ($env:FACESCAN_PY37) { $env:FACESCAN_PYTHON = $env:FACESCAN_PY37 }
    try {
        return Select-Python { param($v) $v.Major -eq 3 -and $v.Minor -eq 7 } '-3.7'
    } finally {
        $env:FACESCAN_PYTHON = $saved
    }
}

# Clean a path typed or pasted by the user: surrounding quotes/whitespace
# (Explorer's "Copy as path" adds quotes) and a trailing backslash (which
# Windows PowerShell 5.1 would turn into an escaped quote on the command line).
function ConvertTo-CleanPath([string]$Path) {
    if ($null -eq $Path) { return '' }
    $p = $Path.Trim().Trim('"').Trim("'").Trim()
    while ($p.Length -gt 3 -and ($p.EndsWith('\') -or $p.EndsWith('/'))) { $p = $p.Substring(0, $p.Length - 1) }
    return $p
}

function Invoke-Python([string[]]$Py, [string[]]$ScriptArgs) {
    $exe = $Py[0]
    $rest = @()
    if ($Py.Count -gt 1) { $rest = $Py[1..($Py.Count - 1)] }
    foreach ($a in $ScriptArgs) {
        # Arguments with embedded double quotes are mangled by Windows PowerShell 5.1.
        if ($a -match '"') { throw "internal error: argument contains a double quote: $a" }
    }
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

# Find Python >= 3.9 or explain exactly what was tried and why each failed.
function Require-Python {
    $py = Find-Python
    if (-not $py) {
        Write-Warn2 'No working Python 3.9 or newer was found.'
        Write-PythonReport 'need 3.9 or newer'
        Write-Host  'Fix: install it with  winget install -e --id Python.Python.3.12'
        Write-Host  '     (or python.org, tick "Add python.exe to PATH"), then run this again.'
        Write-Host  '     If Python IS installed, set FACESCAN_PYTHON to the full path of python.exe and rerun.'
        return $null
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
