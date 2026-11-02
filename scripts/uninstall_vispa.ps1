# VisPa-only uninstall for the explicitly selected Python environment.
# Version: 1.13.0.dev0
# Last updated: 2026-11-02
# Change history: ../CHANGELOG.md
param(
    [Parameter(Mandatory = $true)][string]$Python,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$pythonCommand = Get-Command -Name $Python -ErrorAction Stop
$pythonPath = $pythonCommand.Source
$resolvedPython = & $pythonPath -c 'import sys; print(sys.executable)'
if ($LASTEXITCODE -ne 0 -or -not $resolvedPython) {
    throw "Cannot start the selected Python interpreter: $Python"
}
Write-Host "Python: $resolvedPython"

& $pythonPath -m pip --version
if ($LASTEXITCODE -ne 0) { throw 'pip is unavailable in the selected Python environment' }

& $pythonPath -m pip show vispa *> $null
$vispaPresent = ($LASTEXITCODE -eq 0)
& $pythonPath -m pip show remap *> $null
$remapPresent = ($LASTEXITCODE -eq 0)
if (-not $vispaPresent) {
    Write-Host 'VisPa is already absent from this Python environment.'
    exit 0
}

if ($DryRun) {
    Write-Host "Dry run: $resolvedPython -m pip uninstall --yes vispa"
    Write-Host 'Only the VisPa package would be removed; ReMAP, dependencies, configuration, caches and outputs are not uninstall targets.'
    exit 0
}

& $pythonPath -m pip uninstall --yes vispa
if ($LASTEXITCODE -ne 0) { throw 'VisPa pip uninstall failed' }
& $pythonPath -m pip show vispa *> $null
if ($LASTEXITCODE -eq 0) { throw 'VisPa still appears installed after uninstall' }
if ($remapPresent) {
    & $pythonPath -m pip show remap *> $null
    if ($LASTEXITCODE -ne 0) { throw 'ReMAP was present before uninstall but is now missing' }
}
Write-Host 'VisPa removed from the selected Python environment. ReMAP and user data were left in place.'
