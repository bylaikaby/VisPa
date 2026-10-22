<#
.SYNOPSIS
Install VisPa into a dedicated virtual environment.

Version: 1.11.0.dev1 (local/unreleased)
Last updated: 2026-10-22
Change history: ../CHANGELOG.md

.EXAMPLE
.\tools\install.ps1 -Wheel .\dist\vispa-1.11.0.dev1-py3-none-any.whl -Wheelhouse C:\path\to\wheelhouse -Config C:\data\visual_toolkit_config.yaml

.EXAMPLE
.\tools\install.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'VisPa\venv'),
    [string]$Python = 'py',
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
$sourceMode = -not $Wheel -and (
    $Source -or (Test-Path -LiteralPath (Join-Path $repo 'pyproject.toml'))
)
$venvPython = Join-Path $InstallDir 'Scripts\python.exe'
$plan = [ordered]@{
    install_dir = $InstallDir
    python = $Python
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
if ($Python -eq 'py' -and -not (Get-Command py -ErrorAction SilentlyContinue)) {
    $Python = 'python'
}
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $Python -m venv $InstallDir
    if ($LASTEXITCODE -ne 0) {
        throw "Creating the virtual environment failed with exit code $LASTEXITCODE."
    }
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
    $guiArgs = @()
    if ($Config) { $guiArgs += @('--config', $Config) }
    Start-Process -FilePath $gui -ArgumentList $guiArgs
}
Write-Host "Installed VisPa."
Write-Host "GUI: $gui"
if ($Config) { Write-Host "Config: $Config" }
