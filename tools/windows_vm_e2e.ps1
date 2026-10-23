<#
Version: 1.11.0.dev6 (local/unreleased)
Last updated: 2026-10-23
Change history: ../CHANGELOG.md
Status: candidate

Run one anonymous source-ZIP install in an isolated Windows user profile:
  pwsh -NoProfile -File tools/windows_vm_e2e.ps1 -Commit <40-hex SHA> -EvidenceDir <directory>
Use -DryRun to print the resolved plan without downloading or installing.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{40}$')][string]$Commit,
    [Parameter(Mandatory)][string]$EvidenceDir,
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$evidence = [IO.Path]::GetFullPath($EvidenceDir)
$profile = Join-Path $evidence 'VM profile with spaces'
$download = Join-Path $evidence 'source.zip'
$sourceRoot = Join-Path $evidence 'source with spaces'
$miniforgeRoot = Join-Path $evidence 'miniforge3'
if ($miniforgeRoot -match '[^\x21-\x7E]') {
    throw 'EvidenceDir must use an ASCII path without spaces so Miniforge can bootstrap; the isolated user profile and VisPa runtime still test spaced paths.'
}
$runtime = Join-Path $profile 'LocalAppData\VisPa\conda-env'
$config = Join-Path $profile 'AppData\VisPa\vispa_config.yaml'
$plan = [ordered]@{
    schema = 'vispa.windows-vm-e2e.v1'; commit = $Commit.ToLowerInvariant()
    source_url = "https://github.com/bylaikaby/VisPa/archive/$Commit.zip"
    source_zip = $download; source_root = $sourceRoot
    profile_root = $profile; install_dir = $runtime; config = $config
    miniforge_root = $miniforgeRoot
    evidence_dir = $evidence; mode = 'one-case'
}
if ($DryRun) { $plan | ConvertTo-Json -Depth 4; return }
if (Test-Path -LiteralPath $evidence) { throw "Evidence directory must be new: $evidence" }
New-Item -ItemType Directory -Path $evidence | Out-Null
$steps = [ordered]@{}
$saved = @{}
$variables = @('APPDATA','LOCALAPPDATA','USERPROFILE','VISPA_CONFIG','VISPA_PYTHON',
    'VISPA_WHEELHOUSE','VISUAL_TOOLKIT_CONFIG','PROJECTOME_DATASETS','PYTHONPATH','CONDA_PREFIX',
    'CONDA_EXE','CONDA_DEFAULT_ENV','PYTHONHOME','PYTHONUSERBASE','PATH','TEMP','TMP',
    'VISUAL_TOOLKIT_TEST_INSTALLED')
foreach ($name in $variables) { $saved[$name] = [Environment]::GetEnvironmentVariable($name,'Process') }
try {
    $env:APPDATA = Join-Path $profile 'AppData'
    $env:LOCALAPPDATA = Join-Path $profile 'LocalAppData'
    $env:USERPROFILE = $profile
    $env:TEMP = Join-Path $profile 'Temp'
    $env:TMP = $env:TEMP
    New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
    foreach ($name in @('VISPA_CONFIG','VISPA_PYTHON','VISPA_WHEELHOUSE','VISUAL_TOOLKIT_CONFIG',
            'PROJECTOME_DATASETS','PYTHONPATH','CONDA_PREFIX','CONDA_EXE','CONDA_DEFAULT_ENV',
            'PYTHONHOME','PYTHONUSERBASE')) {
        [Environment]::SetEnvironmentVariable($name,$null,'Process')
    }
    # Run with only Windows and PowerShell system command directories. No
    # inherited Python/Conda launcher is needed for HTTPS ZIP or bootstrap.
    $env:PATH = @(
        (Join-Path $env:SystemRoot 'System32'),
        (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0'),
        $PSHOME
    ) | Select-Object -Unique | Join-String -Separator ';'
    if (Get-Command conda.exe,python.exe -ErrorAction SilentlyContinue) {
        throw 'Inherited Python/Conda command is still on the isolated test PATH'
    }
    $steps.clean_process_profile = 'pass'
    Invoke-WebRequest -Uri $plan.source_url -OutFile $download -UseBasicParsing
    $zipHash = (Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash.ToLowerInvariant()
    Expand-Archive -LiteralPath $download -DestinationPath $sourceRoot
    $top = @(Get-ChildItem -LiteralPath $sourceRoot -Directory)
    if ($top.Count -ne 1 -or -not (Test-Path -LiteralPath (Join-Path $top[0].FullName 'install.cmd'))) {
        throw 'Anonymous ZIP did not contain exactly one VisPa source directory with install.cmd'
    }
    $source = $top[0].FullName
    $steps.anonymous_http_commit_zip = 'pass'
    Push-Location -LiteralPath $source
    try {
        $installerPlan = & .\install.cmd -InstallDir $runtime -MiniforgeRoot $miniforgeRoot -NoLaunch -NoShortcut -DryRun | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0 -or $installerPlan.install_dir -ne $runtime -or
            $installerPlan.config -ne $config -or $installerPlan.bootstrap_conda -ne $true -or
            $installerPlan.bootstrap_root -ne $miniforgeRoot -or $installerPlan.bootstrap_root_selection -ne 'explicit') {
            throw 'Installer did not plan isolated Conda bootstrap and expected paths'
        }
        $steps.installer_dry_run = 'pass'
        & .\install.cmd -InstallDir $runtime -MiniforgeRoot $miniforgeRoot -NoLaunch -NoShortcut
        if ($LASTEXITCODE -ne 0) { throw 'Conda-first source install failed' }
        # The installer changes PATH only in its child process. Direct executable
        # probes need the same Conda DLL search path that VisPa.cmd supplies.
        $env:PATH = "$runtime;$runtime\Library\bin;$runtime\Scripts;$env:PATH"
        $python = Join-Path $runtime 'python.exe'
        if (-not (Test-Path -LiteralPath $python)) { $python = Join-Path $runtime 'Scripts\python.exe' }
        $vispa = Join-Path $runtime 'Scripts\vispa.exe'
        if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $vispa)) {
            throw 'Installed Python or VisPa CLI is missing'
        }
        $version = (& $vispa --version).Trim()
        if ($LASTEXITCODE -ne 0 -or $version -notmatch '^1\.11\.0\.dev6$') { throw "Unexpected installed version: $version" }
        & $python -m pip check
        if ($LASTEXITCODE -ne 0) { throw 'Installed environment has broken dependencies' }
        $modulePath = (& $python -c 'import vispa; print(vispa.__file__)').Trim()
        if ($LASTEXITCODE -ne 0 -or -not $modulePath.StartsWith($runtime,[StringComparison]::OrdinalIgnoreCase)) {
            throw "VisPa imported outside installed runtime: $modulePath"
        }
        $payloadCode = 'from pathlib import Path; import hashlib,json,sys,vispa; src=Path(sys.argv[1])/"src"; dst=Path(vispa.__file__).resolve().parent.parent; allowed=(".py",".yaml"); source={p.relative_to(src).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in src.rglob("*") if p.is_file() and p.suffix in allowed}; installed={p.relative_to(dst).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for pkg in ("vispa","Visual_toolkit") for p in (dst/pkg).rglob("*") if p.is_file() and p.suffix in allowed}; print(json.dumps({"count":len(source),"mismatch":sorted(r for r in source.keys() & installed.keys() if source[r]!=installed[r]),"missing":sorted(source.keys()-installed.keys()),"extra":sorted(installed.keys()-source.keys()),"aggregate_sha256":hashlib.sha256("".join(r+":"+source[r]+";" for r in sorted(source)).encode()).hexdigest()}))'
        $payload = & $python -c $payloadCode $source | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0 -or $payload.count -lt 1 -or $payload.mismatch.Count -or
            $payload.missing.Count -or $payload.extra.Count) {
            throw 'Installed Python/YAML payload does not match downloaded source ZIP'
        }
        $steps.conda_bootstrap_and_install = 'pass'
        if (-not (Test-Path -LiteralPath $config)) { throw 'Per-user config missing' }
        $handlePath = Join-Path $env:APPDATA 'VisPa\install.json'
        $handle = Get-Content -LiteralPath $handlePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($handle.prefix -ne $runtime -or $handle.config -ne $config) {
            throw 'Per-user launcher handle does not match installed prefix and config'
        }
        $launcher = Join-Path $source 'VisPa.cmd'
        Push-Location -LiteralPath $evidence
        try {
            $launchedVersion = (& $launcher --version).Trim()
            if ($LASTEXITCODE -ne 0 -or $launchedVersion -ne $version) {
                throw 'VisPa.cmd did not resolve installed version from another working directory'
            }
            & $launcher config-check --validate-only | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'VisPa.cmd did not resolve selected user config' }
        } finally { Pop-Location }
        $steps.launcher_from_other_directory = 'pass'
        & $vispa config-check --config $config --validate-only | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Installed config validation failed' }
        $exampleOutput = Join-Path $evidence 'public-example'
        & $vispa example --config $config --output-dir $exampleOutput --dry-run | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Public example dry run failed' }
        & $vispa example --config $config --output-dir $exampleOutput | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Real public example download/render failed' }
        $png = @(Get-ChildItem -LiteralPath $exampleOutput -File -Filter '*.png')
        $json = @(Get-ChildItem -LiteralPath $exampleOutput -File -Filter '*.json')
        if ($png.Count -ne 1 -or $json.Count -ne 1 -or $png[0].Length -lt 1000) {
            throw 'Expected one real example PNG and one provenance receipt'
        }
        $exampleReceipt = Get-Content -LiteralPath $json[0].FullName -Raw | ConvertFrom-Json
        if ($exampleReceipt.render.views.Count -ne 4 -or
            $exampleReceipt.render.output_sha256 -ne (Get-FileHash $png[0].FullName -Algorithm SHA256).Hash.ToLowerInvariant()) {
            throw 'Real example render receipt does not match output'
        }
        $steps.public_swc_download_and_3d_morphology = 'pass'
        $configHash = (Get-FileHash -LiteralPath $config -Algorithm SHA256).Hash
        $packageDefault = Join-Path (Split-Path -Parent $modulePath) 'default_config.yaml'
        if (-not (Test-Path -LiteralPath $packageDefault)) { throw 'Installed packaged default is missing' }
        $packageDefaultHash = (Get-FileHash $packageDefault -Algorithm SHA256).Hash
        $default = Join-Path (Split-Path $config) 'vispa_config.default.yaml'
        $defaultHash = if (Test-Path $default) { (Get-FileHash $default -Algorithm SHA256).Hash } else { $null }
        $cache = Join-Path $env:LOCALAPPDATA 'VisPa\cache'
        New-Item -ItemType Directory -Path $cache -Force | Out-Null
        $marker = Join-Path $cache 'preservation-marker.txt'
        Set-Content -LiteralPath $marker -Value 'preserve' -NoNewline
        $markerHash = (Get-FileHash $marker -Algorithm SHA256).Hash
        & .\install.cmd -InstallDir $runtime -MiniforgeRoot $miniforgeRoot -NoLaunch -NoShortcut
        if ($LASTEXITCODE -ne 0) { throw 'Repeat install failed' }
        if ((Get-FileHash $config -Algorithm SHA256).Hash -ne $configHash -or
            (Get-FileHash $marker -Algorithm SHA256).Hash -ne $markerHash -or
            (Get-FileHash $packageDefault -Algorithm SHA256).Hash -ne $packageDefaultHash -or
            ((Test-Path $default) -and (Get-FileHash $default -Algorithm SHA256).Hash -ne $defaultHash)) {
            throw 'Repeat install changed user config, default reference or cache'
        }
        $steps.repeat_install_preservation = 'pass'
        $guiLifecycle = 'import sys,tkinter as tk; from vispa.gui import NeuroVisGUI; root=tk.Tk(); root.withdraw(); app=NeuroVisGUI(root,auto_load=False,config_path=sys.argv[1]); root.update_idletasks(); assert "VisPa "+sys.argv[2] in root.title(); root.destroy()'
        & $python -c $guiLifecycle $config $version
        if ($LASTEXITCODE -ne 0) { throw 'Installed GUI creation/lifecycle failed' }
        $steps.installed_gui_lifecycle = 'pass'
        $env:VISUAL_TOOLKIT_TEST_INSTALLED = '1'
        [Environment]::SetEnvironmentVariable('PYTHONPATH',$null,'Process')
        $guiCheck = 'import sys,unittest,pathlib,vispa; assert pathlib.Path(vispa.__file__).resolve().is_relative_to(pathlib.Path(sys.argv[2]).resolve()); sys.path.insert(0,sys.argv[1]); from test_config_editor import SettingsWindowTests; names=("test_sections_raw_roundtrip_and_external_change_guard","test_default_tab_reset_restore_and_distinct_backups"); suite=unittest.TestSuite(SettingsWindowTests(name) for name in names); result=unittest.TextTestRunner(verbosity=2).run(suite); assert result.wasSuccessful() and not result.skipped, "GUI callback test failed or skipped"'
        & $python -c $guiCheck (Join-Path $source 'tests') $runtime
        if ($LASTEXITCODE -ne 0) { throw 'Real Tk Settings callback test failed or skipped' }
        $steps.tk_settings_callbacks = 'pass'
        $suiteCheck = 'import sys,unittest,pathlib,vispa; runtime=pathlib.Path(sys.argv[2]).resolve(); assert pathlib.Path(vispa.__file__).resolve().is_relative_to(runtime), vispa.__file__; suite=unittest.TestLoader().discover(sys.argv[1]); result=unittest.TextTestRunner(verbosity=1).run(suite); import vispa as loaded; assert pathlib.Path(loaded.__file__).resolve().is_relative_to(runtime), loaded.__file__; assert result.wasSuccessful() and not result.skipped, "Installed suite failed or skipped"'
        & $python -c $suiteCheck (Join-Path $source 'tests') $runtime
        if ($LASTEXITCODE -ne 0) { throw 'Full installed unit suite failed or skipped' }
        $steps.installed_unittest_no_skips = 'pass'
        $glPng = Join-Path $evidence 'opengl-context-render.png'
        $glCode = 'import sys; from vispy import app,scene; from vispy.gloo import gl; from PIL import Image; app.use_app("glfw"); canvas=scene.SceneCanvas(keys=None,size=(320,240),show=True); view=canvas.central_widget.add_view(); scene.visuals.XYZAxis(parent=view.scene); view.camera="turntable"; canvas.app.process_events(); pixels=canvas.render(); assert pixels.shape[0]>=200 and pixels.shape[1]>=300; Image.fromarray(pixels).save(sys.argv[1]); print(gl.glGetString(gl.GL_VERSION)); canvas.close()'
        $glOutput = ''
        $glExit = 1
        try {
            $glOutput = & $python -c $glCode $glPng 2>&1
            $glExit = $LASTEXITCODE
        } catch { $glOutput = $_.Exception.Message }
        if ($glExit -eq 0 -and (Test-Path -LiteralPath $glPng) -and
            (Get-Item -LiteralPath $glPng).Length -gt 1000) {
            $steps.opengl_context_render = 'pass'
            $glStatus = 'pass'
        } else {
            $steps.opengl_context_render = 'unavailable_or_failed'
            $glStatus = 'unavailable_or_failed'
        }
        foreach ($gate in @('clean_process_profile','anonymous_http_commit_zip','installer_dry_run',
                'conda_bootstrap_and_install','launcher_from_other_directory',
                'public_swc_download_and_3d_morphology','repeat_install_preservation',
                'installed_gui_lifecycle','tk_settings_callbacks','installed_unittest_no_skips')) {
            if ($steps[$gate] -ne 'pass') { throw "Mandatory VM gate did not pass: $gate" }
        }
        $glDiagnostic = ($glOutput | Out-String).Trim()
        if (-not $glDiagnostic) { $glDiagnostic = 'No diagnostic output from GL probe' }
        if ($glDiagnostic.Length -gt 1600) { $glDiagnostic = $glDiagnostic.Substring(0,1600) + ' [truncated]' }
        $receipt = [ordered]@{
            schema = 'vispa.windows-vm-e2e.v1'; commit = $Commit.ToLowerInvariant(); source_url = $plan.source_url
            source_zip_sha256 = $zipHash; guest_os = (Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber)
            host_is_pristine_os = $false; inherited_python_conda_hidden_from_process = $true
            installer_plan = $installerPlan; installed_version = $version; installed_module_path = $modulePath
            installed_payload_count = $payload.count; installed_payload_aggregate_sha256 = $payload.aggregate_sha256
            user_config_sha256_after_repeat = $configHash.ToLowerInvariant()
            package_default_sha256_after_repeat = $packageDefaultHash.ToLowerInvariant()
            cache_marker_sha256_after_repeat = $markerHash.ToLowerInvariant()
            real_example_png_sha256 = (Get-FileHash $png[0].FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            real_example_receipt_sha256 = (Get-FileHash $json[0].FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            steps = $steps; opengl_context_render = $glStatus
            opengl_context_output = if ($glStatus -eq 'pass') { (Get-FileHash $glPng -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
            opengl_context_version = if ($glStatus -eq 'pass') { ($glOutput | Out-String).Trim() } else { $null }
            opengl_context_failure = if ($glStatus -eq 'pass') { $null } else { "exit=$glExit; $glDiagnostic" }
            vispa_brain_view_real_operation = 'pending_real_demo_assets_and_visible_review'
            status = if ($glStatus -eq 'pass') { 'partial_real_3d_operation_unverified' } else { 'partial_graphics_unverified' }
        }
        $receipt | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $evidence 'run_receipt.json') -Encoding UTF8
    } finally { Pop-Location }
} catch {
    $steps.failed = $_.Exception.Message
    [ordered]@{schema='vispa.windows-vm-e2e.v1'; commit=$Commit; steps=$steps; status='failed'} |
        ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidence 'run_receipt.json') -Encoding UTF8
    throw
} finally {
    foreach ($name in $variables) { [Environment]::SetEnvironmentVariable($name,$saved[$name],'Process') }
}
exit 0
