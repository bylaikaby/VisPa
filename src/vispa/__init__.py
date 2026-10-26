"""Macaque microscopy visualization and review tools.

Importing the package root does not import Matplotlib, acquisition providers, or
optional image libraries. Public names are loaded on first access.

Version: 1.11.0.dev14 (local/unreleased)
Last updated: 2026-10-26
Change history: ../../CHANGELOG.md
"""
from importlib import import_module
from ._version import __version__

_SETTINGS_NAMES = {"settings_schema", "resolve_settings", "apply_settings"}
_DATA_CHECK_NAMES = {"check", "data_check"}

_TOOLKIT_NAMES = {
    "VisPa", "REVIEW_SETTINGS", "TARGET_MARKER_COLOR", "apply_setting_overrides",
    "review_settings_snapshot", "review_settings_schema", "configure_data_sources", "resolve_widefield_parameters",
    "prepare_sagittal_panel", "render_sagittal_context",
}


def __getattr__(name):
    if name in _SETTINGS_NAMES:
        return getattr(import_module(".settings", __name__), name)
    if name in _DATA_CHECK_NAMES:
        return getattr(import_module(".readiness", __name__), name)
    if name in _TOOLKIT_NAMES:
        return getattr(import_module(".toolkit", __name__), name)
    raise AttributeError(name)


def __dir__():
    return sorted(set(globals()) | _TOOLKIT_NAMES | _SETTINGS_NAMES | _DATA_CHECK_NAMES)
