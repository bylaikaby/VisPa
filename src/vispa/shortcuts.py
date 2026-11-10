"""Create the installed Windows desktop launchers from packaged assets.

Version: 1.21.7 (local/unreleased)
Last updated: 2026-11-09
Change history: ../CHANGELOG.md
Status: candidate
"""
from __future__ import annotations

from importlib import resources
import json
import os
from pathlib import Path
import subprocess
import sys

from .config import config_path


SCHEMA = "vispa.desktop_shortcuts.v1"


def shortcut_specs(config: str | os.PathLike | None = None) -> list[dict]:
    """Return the two package-owned shortcuts without writing them."""
    if os.name != "nt":
        raise RuntimeError("desktop shortcut installation is supported on Windows only")
    if config:
        config_file = Path(os.path.abspath(os.path.expanduser(str(config))))
    else:
        config_file = Path.home() / "AppData" / "Roaming" / "VisPa" / "vispa_config.yaml"
    if not config_file.is_file():
        raise FileNotFoundError(
            f"active VisPa configuration does not exist: {config_file}; "
            "launch VisPa once to create it")
    executable = Path(sys.executable).resolve()
    pythonw = executable.with_name("pythonw.exe")
    target = pythonw if pythonw.is_file() else executable
    with resources.as_file(
            resources.files("vispa").joinpath("assets", "vispa.ico")) as icon:
        icon_path = Path(icon).resolve(strict=True)
        if icon_path.suffix.lower() != ".ico" or not icon_path.is_file():
            raise FileNotFoundError("packaged VisPa .ico asset is unavailable")
        common = {
            "target": str(target),
            "working_directory": str(Path.home()),
            "icon_location": f"{icon_path},0",
        }
        return [
            {
                **common,
                "name": "VisPa.lnk",
                "arguments": f'-I -m vispa gui --config "{config_file}"',
                "description": "VisPa with the active local configuration",
            },
            {
                **common,
                "name": "VisPa Settings.lnk",
                "arguments": (
                    f'-I -m vispa gui --config "{config_file}" '
                    "--no-autoload --settings"),
                "description": "VisPa installation and settings",
            },
        ]


_POWERSHELL_INSTALL = r"""
$ErrorActionPreference = 'Stop'
$desktop = [Environment]::GetFolderPath('Desktop')
$items = $env:VISPA_SHORTCUT_SPECS | ConvertFrom-Json
$shell = New-Object -ComObject WScript.Shell
$verified = @()
foreach ($item in @($items)) {
    $path = Join-Path $desktop $item.name
    $shortcut = $shell.CreateShortcut($path)
    $shortcut.TargetPath = $item.target
    $shortcut.Arguments = $item.arguments
    $shortcut.WorkingDirectory = $item.working_directory
    $shortcut.IconLocation = $item.icon_location
    $shortcut.Description = $item.description
    $shortcut.Save()
    $check = $shell.CreateShortcut($path)
    $verified += [ordered]@{
        path = $path
        target = $check.TargetPath
        arguments = $check.Arguments
        icon_location = $check.IconLocation
        description = $check.Description
    }
}
$verified | ConvertTo-Json -Depth 4 -Compress
"""


def install_desktop_shortcuts(config: str | os.PathLike | None = None,
                              *, dry_run: bool = False) -> dict:
    """Install and verify the VisPa and Settings shortcuts."""
    specs = shortcut_specs(config)
    result = {
        "schema": SCHEMA,
        "dry_run": dry_run,
        "specs": specs,
    }
    if dry_run:
        return result
    environment = os.environ.copy()
    environment["VISPA_SHORTCUT_SPECS"] = json.dumps(specs, ensure_ascii=False)
    process = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         _POWERSHELL_INSTALL],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False, env=environment, timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if process.returncode:
        detail = (process.stderr or process.stdout or "unknown PowerShell failure").strip()
        raise RuntimeError(f"desktop shortcut installation failed: {detail[-1000:]}")
    try:
        installed = json.loads((process.stdout or "").strip())
    except ValueError as exc:
        raise RuntimeError("desktop shortcut verifier returned invalid JSON") from exc
    if not isinstance(installed, list) or len(installed) != len(specs):
        raise RuntimeError("desktop shortcut verifier did not return both launchers")
    result["installed"] = installed
    return result
