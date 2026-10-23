<#
Version: 1.11.0.dev4 (local/unreleased)
Last updated: 2026-10-23
Change history: ../CHANGELOG.md

Run with Windows PowerShell 5.1:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/test_install.ps1
#>
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$installer = Join-Path $repo 'tools\install.ps1'
$realPython = (Get-Command python -ErrorAction Stop).Source
$temp = Join-Path ([IO.Path]::GetTempPath()) ('VisPa installer tests ' + [guid]::NewGuid().ToString('N'))
$guiLog = Join-Path $temp 'gui args.txt'
$savedVispaConfig = $env:VISPA_CONFIG
$savedLegacyConfig = $env:VISUAL_TOOLKIT_CONFIG
$savedPath = $env:PATH
$savedAppData = $env:APPDATA
$savedTestEnv = @{}
foreach ($name in @('VISPA_TEST_BASE_JSON', 'VISPA_TEST_TARGET_JSON', 'VISPA_TEST_LAUNCHER_ARGS', 'VISPA_TEST_FALLBACK_ARGS', 'VISPA_TEST_PIP_LOG', 'VISPA_TEST_GUI_ARGS', 'VISPA_TEST_VISPA_ARGS')) {
    $savedTestEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$env:VISPA_TEST_BASE_JSON = '{"executable":"C:\\fixture\\python.exe","version":[3,13,13],"bits":64}'
$env:VISPA_TEST_TARGET_JSON = '{"executable":"stub","version":[3,13,13],"bits":64}'
$env:VISPA_TEST_LAUNCHER_ARGS = Join-Path $temp 'launcher args.txt'
    $env:VISPA_TEST_FALLBACK_ARGS = Join-Path $temp 'fallback args.txt'
$env:VISPA_TEST_PIP_LOG = Join-Path $temp 'pip calls.txt'
$env:VISPA_TEST_VISPA_ARGS = Join-Path $temp 'vispa args.txt'
$env:VISPA_CONFIG = $null
$env:VISUAL_TOOLKIT_CONFIG = $null
$env:VISPA_TEST_GUI_ARGS = $guiLog
New-Item -ItemType Directory -Path $temp | Out-Null
$env:APPDATA = Join-Path $temp 'appdata'
$defaultConfig = Join-Path $env:APPDATA 'VisPa\vispa_config.yaml'
New-Item -ItemType Directory -Path (Split-Path $defaultConfig) -Force | Out-Null
Set-Content -LiteralPath $defaultConfig -Value 'version: 1' -Encoding UTF8
try {
    $pythonDir = Join-Path $temp 'Python with spaces'
    New-Item -ItemType Directory -Path $pythonDir | Out-Null
    $spacedPython = Join-Path $pythonDir 'python.cmd'
    Set-Content -LiteralPath $spacedPython -Value @(
        '@echo off'
        'echo %VISPA_TEST_BASE_JSON%'
    ) -Encoding ASCII
    $launcher = Join-Path $pythonDir 'py.cmd'
    Set-Content -LiteralPath $launcher -Value @(
        '@echo off'
        'echo %* > "%VISPA_TEST_LAUNCHER_ARGS%"'
        'echo %VISPA_TEST_BASE_JSON%'
    ) -Encoding ASCII
    $env:PATH = "$pythonDir;$savedPath"

    $dryRun = & $installer -Source -DryRun | ConvertFrom-Json
    if ($dryRun.python -ne 'py -3.13' -or $dryRun.python_selection -notmatch 'version 3\.13') {
        throw "Dry run did not resolve the Python 3.13 launcher: $($dryRun | ConvertTo-Json -Compress)"
    }
    Write-Host 'PASS: ordinary dry run resolves py -3.13.'

    $installDir = Join-Path $temp 'install dir with spaces'
    $scriptsDir = Join-Path $installDir 'Scripts'
    New-Item -ItemType Directory -Path $scriptsDir -Force | Out-Null
    $stubSource = @'
using System;
using System.IO;
public static class VisPaInstallerStub {
  public static int Main(string[] args) {
    if (Environment.GetCommandLineArgs()[0].EndsWith("python.exe", StringComparison.OrdinalIgnoreCase)) {
      if (args.Length > 0 && args[0] == "-c" && args[1].Contains("json,sys"))
        Console.WriteLine(Environment.GetEnvironmentVariable("VISPA_TEST_TARGET_JSON"));
      if (args.Length > 1 && args[0] == "-m" && args[1] == "pip")
        File.AppendAllText(Environment.GetEnvironmentVariable("VISPA_TEST_PIP_LOG"), "pip\n");
      return 0;
    }
    if (Environment.GetCommandLineArgs()[0].EndsWith("vispa-gui.exe", StringComparison.OrdinalIgnoreCase))
      File.WriteAllText(Environment.GetEnvironmentVariable("VISPA_TEST_GUI_ARGS"), String.Join("\n", args));
    if (Environment.GetCommandLineArgs()[0].EndsWith("vispa.exe", StringComparison.OrdinalIgnoreCase))
      File.AppendAllText(Environment.GetEnvironmentVariable("VISPA_TEST_VISPA_ARGS"), String.Join(" ", args) + "\n");
    return 0;
  }
}
'@
    Add-Type -TypeDefinition $stubSource -Language CSharp -OutputType ConsoleApplication `
        -OutputAssembly (Join-Path $scriptsDir 'python.exe')
    Add-Type -TypeDefinition $stubSource -Language CSharp -OutputType WindowsApplication `
        -OutputAssembly (Join-Path $scriptsDir 'vispa-gui.exe')
    Add-Type -TypeDefinition $stubSource -Language CSharp -OutputType ConsoleApplication `
        -OutputAssembly (Join-Path $scriptsDir 'vispa.exe')

    Remove-Item -LiteralPath $env:VISPA_TEST_LAUNCHER_ARGS -Force -ErrorAction SilentlyContinue
    & $installer -InstallDir $installDir -Source -NoLaunch -NoPath -NoShortcut
    if ($LASTEXITCODE -ne 0) { throw 'Default launcher install preflight failed.' }
    if (-not (Select-String -LiteralPath $env:VISPA_TEST_VISPA_ARGS -Pattern 'config-check --validate-only --config ' -Quiet)) {
        throw 'Installer did not validate configuration without source-path probes.'
    }
    $launcherArgs = Get-Content -LiteralPath $env:VISPA_TEST_LAUNCHER_ARGS -Raw
    if ($launcherArgs -notmatch '^-3\.13 -c ') { throw "Default did not invoke py -3.13: $launcherArgs" }
    Write-Host 'PASS: ordinary install invokes py -3.13 without a -Python variable.'

    $fallbackLauncher = Join-Path $pythonDir 'py.cmd'
    Set-Content -LiteralPath $fallbackLauncher -Value @(
        '@echo off'
        'echo %* > "%VISPA_TEST_LAUNCHER_ARGS%"'
        'exit /b 1'
    ) -Encoding ASCII
    $fallbackPython = Join-Path $pythonDir 'python.cmd'
    Set-Content -LiteralPath $fallbackPython -Value @(
        '@echo off'
        'echo %* > "%VISPA_TEST_FALLBACK_ARGS%"'
        'echo %VISPA_TEST_BASE_JSON%'
    ) -Encoding ASCII
    Remove-Item -LiteralPath $env:VISPA_TEST_LAUNCHER_ARGS,$env:VISPA_TEST_FALLBACK_ARGS -Force -ErrorAction SilentlyContinue
    & $installer -InstallDir $installDir -Source -NoLaunch -NoPath -NoShortcut
    if ($LASTEXITCODE -ne 0) { throw 'Installer did not recover from an unavailable py -3.13 runtime.' }
    $launcherArgs = Get-Content -LiteralPath $env:VISPA_TEST_LAUNCHER_ARGS -Raw
    $fallbackArgs = Get-Content -LiteralPath $env:VISPA_TEST_FALLBACK_ARGS -Raw
    if ($launcherArgs -notmatch '^-3\.13 -c ' -or $fallbackArgs -notmatch '^-c ') {
        throw "Expected failed py -3.13 probe followed by validated python fallback. Launcher: $launcherArgs Fallback: $fallbackArgs"
    }
    Write-Host 'PASS: unavailable py -3.13 runtime falls back to validated python.'

    & $installer -InstallDir $installDir -Python $realPython -Source -NoLaunch -NoPath -NoShortcut
    if ($LASTEXITCODE -ne 0) { throw "Actual CPython preflight failed for '$realPython'." }
    Write-Host 'PASS: production base preflight executes and parses real CPython JSON.'

    Remove-Item -LiteralPath $guiLog -Force -ErrorAction SilentlyContinue
    & $installer -InstallDir $installDir -Python $spacedPython -Source -NoPath -NoShortcut
    if ($LASTEXITCODE -ne 0) { throw 'Installer failed for the no-config launch case.' }
    $deadline = (Get-Date).AddSeconds(10)
    while (-not (Test-Path -LiteralPath $guiLog) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 100 }
    if (-not (Test-Path -LiteralPath $guiLog)) { throw 'GUI child was not launched for the no-config case.' }
    $defaultArgs = @(Get-Content -LiteralPath $guiLog)
    if ($defaultArgs.Count -ne 2 -or $defaultArgs[0] -ne '--config' -or $defaultArgs[1] -ne $defaultConfig) {
        throw "Default per-user config did not reach GUI: $($defaultArgs -join ' | ')"
    }
    Write-Host 'PASS: default per-user VisPa config reaches GUI.'

    $configDir = Join-Path $temp 'config folder with spaces'
    New-Item -ItemType Directory -Path $configDir | Out-Null
    $config = Join-Path $configDir 'selected settings.yaml'
    Set-Content -LiteralPath $config -Value 'version: 1' -Encoding UTF8
    Remove-Item -LiteralPath $guiLog -Force
    & $installer -InstallDir $installDir -Python $spacedPython -Source -Config $config -NoPath -NoShortcut
    if ($LASTEXITCODE -ne 0) { throw 'Installer failed for the spaced-config launch case.' }
    $deadline = (Get-Date).AddSeconds(10)
    while ((-not (Test-Path -LiteralPath $guiLog) -or (Get-Item -LiteralPath $guiLog).Length -eq 0) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 100 }
    $argsReceived = @(Get-Content -LiteralPath $guiLog)
    if ($argsReceived.Count -ne 2 -or $argsReceived[0] -ne '--config' -or $argsReceived[1] -ne $config) {
        throw "Spaced config was not received as one argument. Received: $($argsReceived -join ' | ')"
    }
    Write-Host 'PASS: spaced config path reaches GUI as one argument under Windows PowerShell.'

    Remove-Item -LiteralPath $guiLog -Force
    & $installer -InstallDir $installDir -Python $spacedPython -Source -NoLaunch -NoPath -NoShortcut
    if ($LASTEXITCODE -ne 0) { throw 'Installer failed for the -NoLaunch case.' }
    Start-Sleep -Milliseconds 300
    if (Test-Path -LiteralPath $guiLog) { throw '-NoLaunch unexpectedly started the GUI.' }
    Write-Host 'PASS: -NoLaunch suppresses the GUI process.'

    $badInstallDir = Join-Path $temp 'must not be created'
    try {
        & $installer -InstallDir $badInstallDir -Python (Join-Path $temp 'missing python.exe') -Source -NoPath -NoShortcut -NoLaunch
        throw 'Installer unexpectedly accepted a missing Python interpreter.'
    } catch {
        if ($_.Exception.Message -like 'Installer unexpectedly*') { throw }
        if ($_.Exception.Message -notmatch 'Python command.*was not found') { throw }
    }
    if (Test-Path -LiteralPath $badInstallDir) { throw 'Missing-Python preflight created the target directory.' }
    Write-Host 'PASS: missing Python fails before creating the target environment.'

    foreach ($invalidPython in @(
        '{"executable":"C:\\fixture\\python.exe","version":[3,13,13],"bits":32}',
        '{"executable":"C:\\fixture\\python.exe","version":[3,9,15],"bits":64}'
    )) {
        $env:VISPA_TEST_BASE_JSON = $invalidPython
        $invalidBaseDir = Join-Path $temp ('invalid base ' + [guid]::NewGuid().ToString('N'))
        try {
            & $installer -InstallDir $invalidBaseDir -Python $spacedPython -Source -NoPath -NoShortcut -NoLaunch
            throw 'Installer unexpectedly accepted an unsupported base Python.'
        } catch {
            if ($_.Exception.Message -like 'Installer unexpectedly*') { throw }
            if ($_.Exception.Message -notmatch 'VisPa requires') { throw }
        }
        if (Test-Path -LiteralPath $invalidBaseDir) { throw 'Invalid base Python created a target environment.' }
    }
    Write-Host 'PASS: 32-bit and pre-3.10 Python fail before target creation.'
    $env:VISPA_TEST_BASE_JSON = '{"executable":"C:\\fixture\\python.exe","version":[3,13,13],"bits":64}'

    $env:VISPA_TEST_TARGET_JSON = '{"executable":"stub","version":[3,13,13],"bits":32}'
    Remove-Item -LiteralPath $env:VISPA_TEST_PIP_LOG -Force -ErrorAction SilentlyContinue
    try {
        & $installer -InstallDir $installDir -Python $spacedPython -Source -NoPath -NoShortcut -NoLaunch
        throw 'Installer unexpectedly accepted an invalid existing target interpreter.'
    } catch {
        if ($_.Exception.Message -like 'Installer unexpectedly*') { throw }
        if ($_.Exception.Message -notmatch 'Target environment requires') { throw }
    }
    if (Test-Path -LiteralPath $env:VISPA_TEST_PIP_LOG) { throw 'Target preflight failure reached pip.' }
    Write-Host 'PASS: invalid existing target Python fails before pip.'
} finally {
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/')
    $tempFullPath = [IO.Path]::GetFullPath($temp).TrimEnd('\', '/')
    $tempLeaf = [IO.Path]::GetFileName($tempFullPath)
    $tempParent = [IO.Path]::GetDirectoryName($tempFullPath).TrimEnd('\', '/')
    if ($tempParent -ne $tempRoot -or $tempLeaf -notmatch '^VisPa installer tests [0-9a-f]{32}$' -or $tempFullPath -eq $tempRoot) {
        throw "Refusing test cleanup outside the verified temporary directory: $tempFullPath"
    }
    Remove-Item -LiteralPath $tempFullPath -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item Env:\VISPA_TEST_GUI_ARGS -ErrorAction SilentlyContinue
    if ($null -eq $savedVispaConfig) { Remove-Item Env:\VISPA_CONFIG -ErrorAction SilentlyContinue }
    else { $env:VISPA_CONFIG = $savedVispaConfig }
    if ($null -eq $savedLegacyConfig) { Remove-Item Env:\VISUAL_TOOLKIT_CONFIG -ErrorAction SilentlyContinue }
    else { $env:VISUAL_TOOLKIT_CONFIG = $savedLegacyConfig }
    $env:PATH = $savedPath
    $env:APPDATA = $savedAppData
    foreach ($name in $savedTestEnv.Keys) {
        if ($null -eq $savedTestEnv[$name]) { Remove-Item "Env:\$name" -ErrorAction SilentlyContinue }
        else { [Environment]::SetEnvironmentVariable($name, [string]$savedTestEnv[$name], 'Process') }
    }
}
