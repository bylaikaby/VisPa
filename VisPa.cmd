@echo off
REM Version: 1.11.0.dev14 (local/unreleased)
REM Last updated: 2026-10-26
REM Change history: CHANGELOG.md
if /I not "%CONDA_DEFAULT_ENV%"=="vispa" (echo Activate the vispa Conda environment first: conda activate vispa 1>&2 & exit /b 1)
python -m vispa %*
exit /b %ERRORLEVEL%
