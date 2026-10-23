<#
Version: 1.11.0.dev6 (local/unreleased)
Last updated: 2026-10-23
Change history: ../CHANGELOG.md
Run: powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/test_install.ps1
#>
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$installer = Join-Path $repo 'tools\install.ps1'
$launcher = Join-Path $repo 'VisPa.cmd'
$environmentFile = Join-Path $repo 'environment.yml'
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($installer,[ref]$tokens,[ref]$errors) | Out-Null
if ($errors.Count) { throw "Installer syntax errors: $($errors -join '; ')" }
Write-Host 'PASS: installer parses in Windows PowerShell.'
foreach ($path in @($launcher,$environmentFile)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing entry point: $path" }
}
$envYaml = Get-Content -LiteralPath $environmentFile -Raw
foreach ($required in @('python=3.13','  - tk','  - scipy','  - vispy=0.17.0','  - pip:','PyGLM==2.8.3')) {
    if (-not $envYaml.Contains($required)) { throw "Missing Conda dependency: $required" }
}
Write-Host 'PASS: Conda definition includes Python, Tk, scientific and 3D dependencies.'
$plan = & $installer -DryRun -NoLaunch -NoShortcut | ConvertFrom-Json
if ($plan.install_dir -notmatch 'VisPa[\\/]conda-env$') { throw "Unexpected default prefix: $($plan.install_dir)" }
if ($plan.add_user_path -ne $false -or $plan.launch_gui -ne $false -or $plan.desktop_shortcut -ne $false) {
    throw 'Dry-run side effect flags are wrong.'
}
if ($plan.runtime_python -notmatch '[\\/]python.exe$' -or $plan.environment_file -ne $environmentFile) {
    throw 'Dry-run did not resolve Conda Python and environment definition.'
}
Write-Host 'PASS: dry run resolves isolated prefix and leaves PATH unchanged.'
$missing = Join-Path $env:TEMP ('VisPa-missing-conda-' + [guid]::NewGuid().ToString('N') + '.exe')
try {
    & $installer -Conda $missing -DryRun | Out-Null
    throw 'Installer accepted missing Conda.'
} catch {
    if ($_.Exception.Message -eq 'Installer accepted missing Conda.') { throw }
    if ($_.Exception.Message -notmatch 'Conda executable does not exist') { throw }
}
Write-Host 'PASS: explicit missing Conda fails with an actionable error.'
try {
    & $installer -Python 'C:\not-used\python.exe' -DryRun | Out-Null
    throw 'Installer accepted obsolete -Python.'
} catch {
    if ($_.Exception.Message -eq 'Installer accepted obsolete -Python.') { throw }
    if ($_.Exception.Message -notmatch 'unsupported.*-Conda') { throw }
}
Write-Host 'PASS: old -Python option explains the new -Conda handle.'
$launcherText = Get-Content -LiteralPath $launcher -Raw
if ($launcherText -notmatch 'LaunchOnly' -or $launcherText -notmatch 'VISPA_ARG_COUNT') {
    throw 'Launcher does not pass arguments to the installed runtime.'
}
$installerText = Get-Content -LiteralPath $installer -Raw
if ($installerText -notmatch 'install.json' -or $installerText -notmatch 'UTF8Encoding' -or $installerText -notmatch 'Library\\bin') {
    throw 'Launcher handle does not preserve Unicode prefix/config or Conda DLL path.'
}
Write-Host 'PASS: launcher resolves Unicode prefix/config and Conda DLL path.'
$savedAppData = $env:APPDATA
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('VisPa launcher test ' + [guid]::NewGuid().ToString('N'))
try {
    $env:APPDATA = Join-Path $testRoot 'profile'
    $prefix = Join-Path $testRoot 'runtime with spaces 中文'
    $scripts = Join-Path $prefix 'Scripts'
    $externalConfig = Join-Path $testRoot 'external 配置\settings file.yaml'
    $log = Join-Path $testRoot 'launch.json'
    New-Item -ItemType Directory -Path $scripts,(Split-Path $externalConfig),(Join-Path $env:APPDATA 'VisPa') -Force | Out-Null
    Set-Content -LiteralPath $externalConfig -Value 'version: 1' -Encoding UTF8
    $stub = @'
using System;
using System.IO;
using System.Text;
using System.Web.Script.Serialization;
public static class LauncherStub {
  public static int Main(string[] args) {
    var record = new { executable = Environment.GetCommandLineArgs()[0], args = args,
      config = Environment.GetEnvironmentVariable("VISPA_CONFIG"), path = Environment.GetEnvironmentVariable("PATH") };
    File.WriteAllText(Environment.GetEnvironmentVariable("VISPA_TEST_LAUNCH_LOG"),
      new JavaScriptSerializer().Serialize(record), new UTF8Encoding(false));
    return 0;
  }
}
'@
    Add-Type -TypeDefinition $stub -ReferencedAssemblies System.Web.Extensions -Language CSharp -OutputType ConsoleApplication -OutputAssembly (Join-Path $scripts 'vispa.exe')
    Add-Type -TypeDefinition $stub -ReferencedAssemblies System.Web.Extensions -Language CSharp -OutputType WindowsApplication -OutputAssembly (Join-Path $scripts 'vispa-gui.exe')
    $handlePath = Join-Path $env:APPDATA 'VisPa\install.json'
    $handleData = @{ prefix = $prefix; config = $externalConfig } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText($handlePath,$handleData,(New-Object System.Text.UTF8Encoding($false)))
    $env:VISPA_TEST_LAUNCH_LOG = $log
    & $launcher --version 'argument with spaces'
    if ($LASTEXITCODE -ne 0) { throw "CLI launcher returned $LASTEXITCODE" }
    $called = Get-Content -LiteralPath $log -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($called.args.Count -ne 2 -or $called.args[0] -ne '--version' -or $called.args[1] -ne 'argument with spaces') { throw 'CLI arguments changed in launcher.' }
    if ($called.config -ne $externalConfig -or $called.path -notlike "$prefix;*") { throw 'Launcher lost selected config or Conda prefix.' }
    Write-Host 'PASS: CLI launcher preserves Unicode prefix, external config and spaced argument.'
    Remove-Item -LiteralPath $log -Force
    & $launcher
    if ($LASTEXITCODE -ne 0) { throw "GUI launcher returned $LASTEXITCODE" }
    $deadline = (Get-Date).AddSeconds(10)
    while (-not (Test-Path -LiteralPath $log) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 100 }
    $called = Get-Content -LiteralPath $log -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($called.args.Count -ne 2 -or $called.args[0] -ne '--config' -or $called.args[1] -ne $externalConfig) { throw 'GUI did not receive external config.' }
    Write-Host 'PASS: GUI launcher receives selected external config.'
} finally {
    $env:APPDATA = $savedAppData
    Remove-Item Env:\VISPA_TEST_LAUNCH_LOG -ErrorAction SilentlyContinue
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\','/')
    $testPath = [IO.Path]::GetFullPath($testRoot).TrimEnd('\','/')
    if ([IO.Path]::GetDirectoryName($testPath).TrimEnd('\','/') -ne $tempRoot -or [IO.Path]::GetFileName($testPath) -notmatch '^VisPa launcher test [0-9a-f]{32}$') {
        throw "Refusing cleanup outside test temp root: $testPath"
    }
    Remove-Item -LiteralPath $testPath -Recurse -Force -ErrorAction SilentlyContinue
}
