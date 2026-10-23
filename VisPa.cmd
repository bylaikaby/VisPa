@echo off
REM Version: 1.11.0.dev6 (local/unreleased)
REM Last updated: 2026-10-23
REM Change history: CHANGELOG.md
setlocal DisableDelayedExpansion
set "VISPA_SCRIPT_DIR=%~dp0"
set "VISPA_ARG_COUNT=0"
:collect
if "%~1"=="" goto run
if %VISPA_ARG_COUNT% GEQ 64 (
  echo VisPa accepts at most 64 launcher arguments. 1>&2
  exit /b 2
)
set "VISPA_ARG_%VISPA_ARG_COUNT%=%~1"
set /a VISPA_ARG_COUNT+=1 >nul
shift
goto collect
:run
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%VISPA_SCRIPT_DIR%tools\install.ps1" -LaunchOnly
exit /b %errorlevel%
