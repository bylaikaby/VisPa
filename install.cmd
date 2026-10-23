@echo off
REM Version: 1.11.0.dev4 (local/unreleased)
REM Last updated: 2026-10-22
REM Change history: CHANGELOG.md
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install.ps1" %*
