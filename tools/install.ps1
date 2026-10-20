<#
.SYNOPSIS
Install VisualToolkit into a dedicated virtual environment.

.EXAMPLE
.\tools\install.ps1 -Wheelhouse D:\projectome_analysis\work\visual_toolkit_extraction\wheelhouse -Config D:\projectome_analysis\main_scripts\Visual_toolkit\visual_toolkit_config.yaml

.EXAMPLE
.\tools\install.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'VisualToolkit\venv'),
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
if (-not $Config -and $env:VISUAL_TOOLKIT_CONFIG) {
    $Config = $env:VISUAL_TOOLKIT_CONFIG
}
if (-not $Wheelhouse -and $env:VISUAL_TOOLKIT_WHEELHOUSE) {
    $Wheelhouse = $env:VISUAL_TOOLKIT_WHEELHOUSE
}
if (-not $Wheel -and -not $Source) {
    $wheels = Get-ChildItem -Path (Join-Path $repo 'dist') -Recurse `
        -Filter 'visual_toolkit-*.whl' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending
    if ($wheels) { $Wheel = $wheels[0].FullName }
}
$sourceMode = $Source -or (-not $Wheel -and (Test-Path (Join-Path $repo 'pyproject.toml')))
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
    throw "No wheel found under $repo\dist and no pyproject.toml is present."
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
    "visual-toolkit[3d] @ file:///$($Wheel.Replace('\', '/'))"
} else {
    'visual-toolkit[3d]'
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
    & (Join-Path $InstallDir 'Scripts\visual-toolkit.exe') @pathArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Registering the user PATH failed with exit code $LASTEXITCODE."
    }
}
$gui = Join-Path $InstallDir 'Scripts\visual-toolkit-gui.exe'
if (-not $NoShortcut) {
    try {
        $desktop = [Environment]::GetFolderPath('Desktop')
        $shortcutPath = Join-Path $desktop 'VisualToolkit.lnk'
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $gui
        if ($Config) { $shortcut.Arguments = "--config `"$Config`"" }
        $shortcut.WorkingDirectory = Split-Path $gui
        $shortcut.Description = 'VisualToolkit review GUI'
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
Write-Host "Installed VisualToolkit."
Write-Host "GUI: $gui"
if ($Config) { Write-Host "Config: $Config" }
