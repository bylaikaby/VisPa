@echo off
REM Version: 1.11.0.dev6 (local/unreleased)
REM Last updated: 2026-10-23
REM Change history: CHANGELOG.md
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install.ps1" %*
