<#
Version: 1.11.0.dev14 (local/unreleased)
Last updated: 2026-10-26
Change history: ../CHANGELOG.md
#>
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$installer = Join-Path $repo 'tools\install.ps1'
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($installer, [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count) { throw "Installer syntax errors: $($errors -join '; ')" }
$missing = Join-Path $env:TEMP 'vispa-no-conda-python.exe'
try { & $installer -CondaBasePython $missing; throw 'Missing Conda base Python was accepted.' }
catch { if ($_.Exception.Message -notmatch 'Conda base Python not found') { throw } }
Write-Host 'PASS: installer parses and rejects missing Conda before writes.'
