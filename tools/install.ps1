<#
Version: 1.11.0.dev14 (local/unreleased)
Last updated: 2026-10-26
Change history: ../CHANGELOG.md
Status: candidate
#>
[CmdletBinding()]
param([string]$CondaBasePython = $(if ($env:CONDA_PYTHON_EXE) { $env:CONDA_PYTHON_EXE } else { "$env:USERPROFILE\miniconda3\python.exe" }))

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$yaml = Join-Path $repo 'environment.yml'
if (-not (Test-Path -LiteralPath $CondaBasePython -PathType Leaf)) {
    throw "Conda base Python not found: $CondaBasePython. Open Miniforge Prompt and run the README commands, or pass -CondaBasePython PATH."
}
& $CondaBasePython -m conda --version
if ($LASTEXITCODE -ne 0) { throw 'Conda is unavailable in the selected base Python.' }
$base = Split-Path -Parent $CondaBasePython
$prefix = Join-Path $base 'envs\vispa'
if (Test-Path -LiteralPath (Join-Path $prefix 'conda-meta\history') -PathType Leaf) {
    & $CondaBasePython -m conda env update --prefix $prefix -f $yaml
} else {
    if (Test-Path -LiteralPath $prefix) { throw "Target exists but is not a Conda environment: $prefix" }
    & $CondaBasePython -m conda env create --prefix $prefix -f $yaml
}
if ($LASTEXITCODE -ne 0) { throw 'Conda environment setup failed.' }

$python = Join-Path $prefix 'python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "VisPa Python not found: $python" }
& $python -m pip install --no-build-isolation -e "$repo[3d,tiff]"
if ($LASTEXITCODE -ne 0) { throw 'VisPa package installation failed.' }
& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed.' }
& $python -m vispa --version
if ($LASTEXITCODE -ne 0) { throw 'VisPa command failed.' }
Write-Host "Installed with $python. Activate vispa before running VisPa.cmd."
