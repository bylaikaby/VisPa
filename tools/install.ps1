<#
.SYNOPSIS
Install VisPa into a dedicated virtual environment.

Version: 1.11.0.dev2 (local/unreleased)
Last updated: 2026-10-22
Change history: ../CHANGELOG.md

.EXAMPLE
.\tools\install.ps1 -Wheel .\dist\vispa-1.11.0.dev2-py3-none-any.whl -Wheelhouse C:\path\to\wheelhouse -Config C:\data\visual_toolkit_config.yaml

.EXAMPLE
.\tools\install.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'VisPa\venv'),
    [string]$Python = '',
    [string]$Wheel = '',
    [string]$Wheelhouse = '',
    [string]$Config = '',
    [switch]$Source,
    [switch]$NoPath,
    [switch]$NoLaunch,
    [switch]$NoShortcut,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if (-not $Config -and $env:VISPA_CONFIG) { $Config = $env:VISPA_CONFIG }
if (-not $Config -and $env:VISUAL_TOOLKIT_CONFIG) {
    $Config = $env:VISUAL_TOOLKIT_CONFIG
}
if (-not $Wheelhouse -and $env:VISPA_WHEELHOUSE) { $Wheelhouse = $env:VISPA_WHEELHOUSE }
if (-not $Wheelhouse -and $env:VISUAL_TOOLKIT_WHEELHOUSE) {
    $Wheelhouse = $env:VISUAL_TOOLKIT_WHEELHOUSE
}
if ($Wheel -and $Source) {
    throw 'Choose either -Wheel or -Source; the options cannot be used together.'
}
$pythonCommand = $Python
$pythonPrefix = @()
$pythonSelection = 'explicit -Python executable path'
$allowPythonFallback = $false
if (-not $Python) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $pythonCommand = 'py'
        $pythonPrefix = @('-3.13')
        $pythonSelection = 'Python launcher, version 3.13'
        $allowPythonFallback = $true
    } else {
        $pythonCommand = 'python'
        $pythonSelection = 'python command fallback; version checked before installation'
    }
} elseif ($Python -eq 'py') {
    $pythonCommand = 'py'
    $pythonPrefix = @('-3.13')
    $pythonSelection = 'explicit Python launcher, version 3.13'
}
$pythonPlan = (@($pythonCommand) + $pythonPrefix) -join ' '
$sourceMode = -not $Wheel -and (
    $Source -or (Test-Path -LiteralPath (Join-Path $repo 'pyproject.toml'))
)
$venvPython = Join-Path $InstallDir 'Scripts\python.exe'
$plan = [ordered]@{
    install_dir = $InstallDir
    python = $pythonPlan
    python_selection = $pythonSelection
    wheel = $Wheel
    wheelhouse = $Wheelhouse
    config = $Config
    source_install = $sourceMode
    add_user_path = (-not $NoPath)
    launch_gui = (-not $NoLaunch)
    desktop_shortcut = (-not $NoShortcut)
}
if ($DryRun) {
    $plan | ConvertTo-Json
    return
}
if (-not $Wheel -and -not $sourceMode) {
    throw "No source checkout or explicit wheel was provided for $repo."
}
$resolvedCommand = Get-Command $pythonCommand -ErrorAction SilentlyContinue
if (-not $resolvedCommand) {
    throw "Python command '$pythonCommand' was not found. Install 64-bit Python 3.13 or pass its full path with -Python."
}
$pythonProbe = 'import json,sys; import pip,tkinter; tkinter.Tcl(); print(json.dumps(dict(executable=sys.executable,version=list(sys.version_info[:3]),bits=sys.maxsize.bit_length()+1)))'
$previousErrorAction = $ErrorActionPreference
try {
    $ErrorActionPreference = 'Continue'
    $pythonDetailsRaw = & $pythonCommand @pythonPrefix -c $pythonProbe 2>&1
    $pythonExitCode = $LASTEXITCODE
} finally { $ErrorActionPreference = $previousErrorAction }
if ($pythonExitCode -ne 0) {
    $launcherFailure = $pythonDetailsRaw
    $fallbackCommand = if ($allowPythonFallback) { Get-Command python -ErrorAction SilentlyContinue } else { $null }
    if ($fallbackCommand) {
        $pythonCommand = 'python'
        $pythonPrefix = @()
        $pythonSelection = 'python command fallback; version checked before installation'
        $previousErrorAction = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $pythonDetailsRaw = & $pythonCommand -c $pythonProbe 2>&1
            $pythonExitCode = $LASTEXITCODE
        } finally { $ErrorActionPreference = $previousErrorAction }
    }
    if ($pythonExitCode -ne 0) {
        $fallbackFailure = if ($fallbackCommand) { " Fallback 'python' details: $pythonDetailsRaw" } else { '' }
        throw "Python preflight failed for '$($plan.python)'. Install Python 3.13 with pip and Tcl/Tk, or pass its full path with -Python. Launcher details: $launcherFailure.$fallbackFailure"
    }
}
try { $pythonDetails = ($pythonDetailsRaw | Out-String | ConvertFrom-Json -ErrorAction Stop) }
catch { throw "Python preflight returned invalid details for '$pythonCommand': $pythonDetailsRaw" }
if ($pythonDetails.bits -ne 64) {
    throw "VisPa requires 64-bit Python; '$($pythonDetails.executable)' is $($pythonDetails.bits)-bit."
}
if ($pythonDetails.version[0] -ne 3 -or $pythonDetails.version[1] -lt 10) {
    throw "VisPa requires Python 3.10 or newer; found $($pythonDetails.version -join '.')."
}
$Python = [string]$pythonDetails.executable
Write-Host "Python preflight passed: $Python ($($pythonDetails.version -join '.'); $($pythonDetails.bits)-bit; pip and Tk available)."
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $Python -m venv $InstallDir
    if ($LASTEXITCODE -ne 0) {
        throw "Creating the virtual environment failed with exit code $LASTEXITCODE."
    }
}
$previousErrorAction = $ErrorActionPreference
try {
    $ErrorActionPreference = 'Continue'
    $targetPythonRaw = & $venvPython -c $pythonProbe 2>&1
    $targetPythonExitCode = $LASTEXITCODE
} finally { $ErrorActionPreference = $previousErrorAction }
if ($targetPythonExitCode -ne 0) {
    throw "Target environment Python preflight failed at '$venvPython'. Repair or choose a fresh -InstallDir. Details: $targetPythonRaw"
}
try { $targetPythonDetails = ($targetPythonRaw | Out-String | ConvertFrom-Json -ErrorAction Stop) }
catch { throw "Target environment Python returned invalid preflight details at '$venvPython': $targetPythonRaw" }
if ($targetPythonDetails.bits -ne 64 -or $targetPythonDetails.version[0] -ne 3 -or $targetPythonDetails.version[1] -lt 10) {
    throw "Target environment requires 64-bit Python 3.10 or newer; found $($targetPythonDetails.version -join '.') / $($targetPythonDetails.bits)-bit. Repair it or choose a fresh -InstallDir."
}

# Legacy and primary distributions share compatibility filenames; never overlap owners.
& $venvPython -c "import importlib.metadata as m,sys; sys.exit(2 if any(d.metadata['Name'].lower().replace('_','-')=='visual-toolkit' for d in m.distributions()) else 0)"
if ($LASTEXITCODE -eq 2) {
    throw 'Target contains visual-toolkit distribution. Choose a fresh VisPa InstallDir; existing installation is preserved.'
}
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect target distribution ownership.' }
$pipArgs = @('-m', 'pip', 'install', '--disable-pip-version-check', '--upgrade')
if ($Wheelhouse) {
    $pipArgs += @(
        '--no-index',
        '--find-links', (Join-Path $Wheelhouse 'runtime-py313'),
        '--find-links', (Join-Path $Wheelhouse 'optional-py313')
    )
}
$spec = if ($sourceMode) {
    '.[3d]'
} elseif ($Wheel) {
    "vispa[3d] @ file:///$($Wheel.Replace('\', '/'))"
} else {
    'vispa[3d]'
}
$pipArgs += $spec
if ($sourceMode) {
    Push-Location $repo
    try {
        & $venvPython @pipArgs
        if ($LASTEXITCODE -ne 0) {
            throw "pip install failed with exit code $LASTEXITCODE."
        }
    } finally { Pop-Location }
} else {
    & $venvPython @pipArgs
    if ($LASTEXITCODE -ne 0) {
        throw "pip install failed with exit code $LASTEXITCODE."
    }
}

if (-not $NoPath) {
    $pathArgs = @('install-path')
    if ($Config) { $pathArgs += @('--config', $Config) }
    & (Join-Path $InstallDir 'Scripts\vispa.exe') @pathArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Registering the user PATH failed with exit code $LASTEXITCODE."
    }
}
$gui = Join-Path $InstallDir 'Scripts\vispa-gui.exe'
if (-not $NoShortcut) {
    try {
        $desktop = [Environment]::GetFolderPath('Desktop')
        $shortcutPath = Join-Path $desktop 'VisPa.lnk'
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $gui
        if ($Config) { $shortcut.Arguments = "--config `"$Config`"" }
        $shortcut.WorkingDirectory = Split-Path $gui
        $shortcut.Description = 'VisPa review GUI'
        $shortcut.Save()
        Write-Host "Desktop shortcut: $shortcutPath"
    } catch {
        Write-Warning "Could not create the desktop shortcut: $_"
    }
}
if (-not $NoLaunch) {
    try {
        if ($Config) {
            Start-Process -FilePath $gui -ArgumentList @('--config', "`"$Config`"")
        } else {
            Start-Process -FilePath $gui
        }
    } catch {
        throw "Package installation completed, but the GUI did not launch. Once dependencies are installed, start '$gui' directly. Launch error: $_"
    }
}
Write-Host 'Package installation completed.'
if (-not $NoLaunch) { Write-Host 'GUI launch requested.' }
Write-Host "GUI: $gui"
if ($Config) { Write-Host "Config: $Config" }
