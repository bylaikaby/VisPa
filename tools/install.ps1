<#
.SYNOPSIS
Install VisPa in a dedicated Conda environment without activation.
Version: 1.11.0.dev6 (local/unreleased)
Last updated: 2026-10-23
Change history: ../CHANGELOG.md
#>
[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'VisPa\conda-env'),
    [string]$Conda = '',
    [string]$Python = '',
    [string]$Wheel = '',
    [string]$Wheelhouse = '',
    [string]$Config = '',
    [switch]$Source,
    [switch]$NoPath,
    [switch]$NoLaunch,
    [switch]$NoShortcut,
    [switch]$DryRun,
    [switch]$NoBootstrap,
    [switch]$LaunchOnly
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$environmentFile = Join-Path $repo 'environment.yml'
$launcher = Join-Path $repo 'VisPa.cmd'
if ($LaunchOnly) {
    $handle = Join-Path $env:APPDATA 'VisPa\install.json'
    if (-not (Test-Path -LiteralPath $handle -PathType Leaf)) { throw "VisPa is not installed for this user. Run install.cmd first: $handle" }
    $install = Get-Content -LiteralPath $handle -Raw -Encoding UTF8 | ConvertFrom-Json
    $prefix = [string]$install.prefix
    $launchConfig = [string]$install.config
    $cli = Join-Path $prefix 'Scripts\vispa.exe'
    $gui = Join-Path $prefix 'Scripts\vispa-gui.exe'
    if (-not (Test-Path -LiteralPath $cli -PathType Leaf)) { throw "VisPa runtime is missing at $prefix. Rerun install.cmd to repair it." }
    if (-not (Test-Path -LiteralPath $launchConfig -PathType Leaf)) { throw "VisPa config is missing: $launchConfig" }
    $env:PATH = "$prefix;$prefix\Library\bin;$prefix\Scripts;$env:PATH"
    $env:VISPA_CONFIG = $launchConfig
    $count = 0
    if ($env:VISPA_ARG_COUNT) { $count = [int]$env:VISPA_ARG_COUNT }
    if ($count -lt 0 -or $count -gt 64) { throw 'Invalid launcher argument count.' }
    if ($count -eq 0) { & $gui --config $launchConfig; exit $LASTEXITCODE }
    $launchArgs = @()
    for ($i = 0; $i -lt $count; $i++) { $launchArgs += [Environment]::GetEnvironmentVariable("VISPA_ARG_$i", 'Process') }
    & $cli @launchArgs
    exit $LASTEXITCODE
}
if ($Python) { throw '-Python is unsupported by the Conda installer. Pass -Conda with conda.exe instead.' }
if ($Wheel -and $Source) { throw 'Choose either -Wheel or -Source.' }
if ($Wheel -and -not (Test-Path -LiteralPath $Wheel -PathType Leaf)) { throw "Wheel does not exist: $Wheel" }
if (-not (Test-Path -LiteralPath $environmentFile -PathType Leaf)) { throw "Missing $environmentFile" }
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw "Missing $launcher" }
if ($Wheelhouse -and -not (Test-Path -LiteralPath $Wheelhouse -PathType Container)) { throw "Wheelhouse does not exist: $Wheelhouse" }
if ($NoPath) { Write-Warning '-NoPath is retained for compatibility; PATH is never changed.' }
if (-not $Config -and $env:VISPA_CONFIG) { $Config = $env:VISPA_CONFIG }
$userConfig = Join-Path $env:APPDATA 'VisPa\vispa_config.yaml'
$previousHandle = Join-Path $env:APPDATA 'VisPa\install.json'
if (-not $Config -and (Test-Path -LiteralPath $previousHandle -PathType Leaf)) {
    $previousInstall = Get-Content -LiteralPath $previousHandle -Raw -Encoding UTF8 | ConvertFrom-Json
    $Config = [string]$previousInstall.config
}
$configSelection = if ($Config) { 'selected_existing' } elseif (Test-Path -LiteralPath $userConfig -PathType Leaf) {
    $Config = $userConfig
    'existing_per_user'
} else {
    $Config = $userConfig
    'create_from_package_defaults'
}
if ($Config) { $Config = [IO.Path]::GetFullPath($Config) }
if (-not $Wheelhouse -and $env:VISPA_WHEELHOUSE) { $Wheelhouse = $env:VISPA_WHEELHOUSE }
$sourceMode = -not $Wheel -and ($Source -or (Test-Path -LiteralPath (Join-Path $repo 'pyproject.toml')))
if (-not $sourceMode -and -not $Wheel) { throw 'A source checkout or -Wheel is required.' }
$InstallDir = [IO.Path]::GetFullPath($InstallDir)
$targetPython = Join-Path $InstallDir 'python.exe'
$targetCli = Join-Path $InstallDir 'Scripts\vispa.exe'
function Find-Conda([string]$Explicit) {
    if ($Explicit) {
        if (-not (Test-Path -LiteralPath $Explicit -PathType Leaf)) { throw "Conda executable does not exist: $Explicit" }
        return [IO.Path]::GetFullPath($Explicit)
    }
    $command = Get-Command conda.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($candidate in @(
        (Join-Path $env:LOCALAPPDATA 'VisPa\miniforge3\Scripts\conda.exe'),
        (Join-Path $env:USERPROFILE 'miniforge3\Scripts\conda.exe'),
        (Join-Path $env:USERPROFILE 'miniconda3\Scripts\conda.exe'),
        (Join-Path $env:USERPROFILE 'anaconda3\Scripts\conda.exe')
    )) { if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate } }
    return ''
}
$condaExe = Find-Conda $Conda
$bootstrap = -not $condaExe
$bootstrapRoot = Join-Path $env:LOCALAPPDATA 'VisPa\miniforge3'
if ($bootstrap -and $NoBootstrap) { throw 'Conda was not found. Install Miniforge or pass -Conda PATH.' }
if ($bootstrap -and (Test-Path -LiteralPath $bootstrapRoot)) {
    throw "Miniforge bootstrap folder exists without conda.exe: $bootstrapRoot. Pass another -Conda or repair that installation."
}
$plan = [ordered]@{
    install_dir = $InstallDir
    conda = $condaExe
    conda_selection = if ($Conda) { 'explicit' } elseif ($bootstrap) { 'bootstrap_miniforge' } else { 'discovered' }
    bootstrap_conda = $bootstrap
    bootstrap_root = $bootstrapRoot
    environment_file = $environmentFile
    source_root = $repo
    source_install = $sourceMode
    wheel = $Wheel
    wheelhouse = $Wheelhouse
    config = $Config
    config_selection = $configSelection
    cache_root = (Join-Path $env:LOCALAPPDATA 'VisPa\cache')
    output_root = (Join-Path $env:LOCALAPPDATA 'VisPa\output')
    runtime_python = $targetPython
    launcher = $launcher
    add_user_path = $false
    launch_gui = (-not $NoLaunch)
    desktop_shortcut = (-not $NoShortcut)
}
if ($DryRun) { $plan | ConvertTo-Json; return }
if ($configSelection -ne 'create_from_package_defaults' -and -not (Test-Path -LiteralPath $Config -PathType Leaf)) {
    throw "Selected VisPa config does not exist: $Config"
}
if ((Test-Path -LiteralPath $InstallDir) -and -not (Test-Path -LiteralPath (Join-Path $InstallDir 'conda-meta\history') -PathType Leaf)) {
    throw "Target is not a Conda environment: $InstallDir. Files are preserved; choose a fresh -InstallDir."
}
if ($bootstrap) {
    # Pin the official Miniforge release and verify its HTTPS checksum before execution.
    $version = '26.7.2-1'
    $fileName = "Miniforge3-$version-Windows-x86_64.exe"
    $url = "https://github.com/conda-forge/miniforge/releases/download/$version/$fileName"
    $downloadRoot = Join-Path $env:TEMP ('VisPa-miniforge-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $downloadRoot | Out-Null
    $downloadPath = Join-Path $downloadRoot $fileName
    $checksumResponse = Invoke-WebRequest -Uri "$url.sha256" -UseBasicParsing
    $checksum = if ($checksumResponse.Content -is [byte[]]) {
        [Text.Encoding]::ASCII.GetString($checksumResponse.Content)
    } else { [string]$checksumResponse.Content }
    if ($checksum -notmatch ('(?i)^\s*(?<hash>[0-9a-f]{64})\s+\*?' + [regex]::Escape($fileName) + '\s*$')) {
        throw 'Official Miniforge checksum response has an unexpected format.'
    }
    $expected = $Matches['hash'].ToLowerInvariant()
    Invoke-WebRequest -Uri $url -OutFile $downloadPath -UseBasicParsing
    $actual = (Get-FileHash -LiteralPath $downloadPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) { throw "Miniforge SHA256 mismatch: expected $expected, received $actual" }
    New-Item -ItemType Directory -Path (Split-Path $bootstrapRoot) -Force | Out-Null
    $arguments = @('/InstallationType=JustMe', '/AddToPath=0', '/RegisterPython=0', '/S', "/D=$bootstrapRoot")
    $process = Start-Process -FilePath $downloadPath -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -ne 0) { throw "Miniforge install failed: exit $($process.ExitCode). Download retained at $downloadPath" }
    $condaExe = Join-Path $bootstrapRoot 'Scripts\conda.exe'
    if (-not (Test-Path -LiteralPath $condaExe -PathType Leaf)) { throw "Miniforge returned success but conda.exe is missing: $condaExe" }
    Remove-Item -LiteralPath $downloadPath -Force
    Remove-Item -LiteralPath $downloadRoot
}
& $condaExe --version
if ($LASTEXITCODE -ne 0) { throw "Conda cannot run: $condaExe" }
if (Test-Path -LiteralPath (Join-Path $InstallDir 'conda-meta\history')) {
    & $condaExe env update --prefix $InstallDir --file $environmentFile
} else {
    & $condaExe env create --prefix $InstallDir --file $environmentFile --yes
}
if ($LASTEXITCODE -ne 0) { throw "Conda setup failed for $InstallDir. The prefix is preserved for repair." }
if (-not (Test-Path -LiteralPath $targetPython -PathType Leaf)) { throw "Conda Python missing: $targetPython" }
$env:PATH = "$InstallDir;$InstallDir\Library\bin;$InstallDir\Scripts;$env:PATH"
& $targetPython -c 'import sys,tkinter; tkinter.Tcl(); assert sys.version_info[:2] == (3,13); assert sys.maxsize > 2**32'
if ($LASTEXITCODE -ne 0) { throw 'Conda preflight failed: 64-bit Python 3.13 with Tk is required.' }
& $targetPython -c "import importlib.metadata as m,sys; sys.exit(2 if any(d.metadata['Name'].lower().replace('_','-')=='visual-toolkit' for d in m.distributions()) else 0)"
if ($LASTEXITCODE -eq 2) { throw 'Target contains visual-toolkit; choose a fresh -InstallDir. Existing files are preserved.' }
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect target package ownership.' }
$stage = ''
if ($sourceMode) {
    # Setuptools can reuse stale build/lib and egg-info from a dirty checkout.
    # Stage only declared package sources; the original checkout is never cleaned.
    $stage = Join-Path $env:TEMP ('VisPa-source-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $stage | Out-Null
    foreach ($name in @('pyproject.toml','README.md')) {
        Copy-Item -LiteralPath (Join-Path $repo $name) -Destination (Join-Path $stage $name)
    }
    foreach ($packageName in @('vispa','Visual_toolkit')) {
        $packageRoot = Join-Path $repo "src\$packageName"
        if (-not (Test-Path -LiteralPath (Join-Path $packageRoot '__init__.py') -PathType Leaf)) { throw "Missing package source: $packageRoot" }
        foreach ($sourceFile in (Get-ChildItem -LiteralPath $packageRoot -Recurse -File | Where-Object { $_.Extension -in '.py','.yaml' })) {
            $relative = $sourceFile.FullName.Substring($repo.Length + 1)
            $destination = Join-Path $stage $relative
            New-Item -ItemType Directory -Path (Split-Path $destination) -Force | Out-Null
            Copy-Item -LiteralPath $sourceFile.FullName -Destination $destination
        }
    }
}
$pipArgs = @('-m','pip','install','--disable-pip-version-check','--no-deps','--force-reinstall')
if ($Wheelhouse) { $pipArgs += @('--no-index','--find-links',$Wheelhouse) }
$package = if ($Wheel) { [IO.Path]::GetFullPath($Wheel) } else { $stage }
$pipArgs += $package
& $targetPython @pipArgs
if ($LASTEXITCODE -ne 0) { throw 'Installing VisPa into Conda failed.' }
if ($sourceMode) {
    $installedRoot = Join-Path $InstallDir 'Lib\site-packages'
    $sourceFiles = @(Get-ChildItem -LiteralPath (Join-Path $stage 'src\vispa'),(Join-Path $stage 'src\Visual_toolkit') -Recurse -File | Where-Object { $_.Extension -in '.py','.yaml' })
    $installedFiles = @(Get-ChildItem -LiteralPath (Join-Path $installedRoot 'vispa'),(Join-Path $installedRoot 'Visual_toolkit') -Recurse -File | Where-Object { $_.Extension -in '.py','.yaml' })
    if ($sourceFiles.Count -ne $installedFiles.Count) { throw "Installed payload count $($installedFiles.Count) differs from source $($sourceFiles.Count). Staging retained: $stage" }
    foreach ($sourceFile in $sourceFiles) {
        $relative = $sourceFile.FullName.Substring((Join-Path $stage 'src').Length + 1)
        $installedFile = Join-Path $installedRoot $relative
        if (-not (Test-Path -LiteralPath $installedFile -PathType Leaf)) { throw "Installed file is missing: $relative. Staging retained: $stage" }
        if ((Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $installedFile -Algorithm SHA256).Hash) {
            throw "Installed file differs from source: $relative. Staging retained: $stage"
        }
    }
    $tempRoot = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\','/')
    $stageFull = [IO.Path]::GetFullPath($stage).TrimEnd('\','/')
    if ([IO.Path]::GetDirectoryName($stageFull).TrimEnd('\','/') -ne $tempRoot -or [IO.Path]::GetFileName($stageFull) -notmatch '^VisPa-source-[0-9a-f]{32}$') {
        throw "Refusing staging cleanup outside the verified temp root: $stageFull"
    }
    Remove-Item -LiteralPath $stageFull -Recurse -Force
    Write-Host "Installed payload verified: $($sourceFiles.Count) Python/YAML files exact."
}
if (-not (Test-Path -LiteralPath $targetCli -PathType Leaf) -or -not (Test-Path -LiteralPath (Join-Path $InstallDir 'Scripts\vispa-gui.exe') -PathType Leaf)) {
    throw 'VisPa CLI or GUI executable is missing after package installation.'
}
& $targetPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed. The environment is preserved for repair.' }
if ($configSelection -eq 'create_from_package_defaults') {
    New-Item -ItemType Directory -Path (Split-Path $Config) -Force | Out-Null
    & $targetCli config-init --output $Config
    if ($LASTEXITCODE -ne 0) { throw "Could not create per-user config: $Config" }
}
& $targetCli config-check --validate-only --config $Config
if ($LASTEXITCODE -ne 0) { throw "VisPa config validation failed: $Config" }
$handle = Join-Path $env:APPDATA 'VisPa\install.json'
New-Item -ItemType Directory -Path (Split-Path $handle) -Force | Out-Null
$handleValue = [ordered]@{ prefix = $InstallDir; config = [IO.Path]::GetFullPath($Config) } | ConvertTo-Json -Compress
$existingHandle = if (Test-Path -LiteralPath $handle -PathType Leaf) { Get-Content -LiteralPath $handle -Raw -Encoding UTF8 } else { '' }
if ($existingHandle -ne $handleValue) {
    [IO.File]::WriteAllText($handle, $handleValue, (New-Object System.Text.UTF8Encoding($false)))
}
if (-not $NoShortcut) {
    try {
        $desktop = [Environment]::GetFolderPath('Desktop')
        $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktop 'VisPa.lnk'))
        $shortcut.TargetPath = $launcher
        $shortcut.WorkingDirectory = $repo
        $shortcut.Description = 'VisPa review GUI'
        $shortcut.Save()
    } catch { Write-Warning "Desktop shortcut could not be created: $_" }
}
Write-Host "VisPa installed in Conda environment: $InstallDir"
Write-Host "Launcher: $launcher"
Write-Host "Config: $Config"
if (-not $NoLaunch) {
    Start-Process -FilePath $launcher -WorkingDirectory $repo -WindowStyle Hidden
    Write-Host 'GUI launch requested.'
}
