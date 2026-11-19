"""ReMAP local candidate API.

Sibling analysis surfaces (loaded on first access):

- ``region_analysis`` / population workbook names
- ``morph_clustering`` (FNT pipeline, clustering checks, NeuroM features)

Version: 0.1.0.dev45 (local/unreleased)
Last updated: 2026-11-10
Change history:
- 2026-11-10: Lazy exports follow region_analysis, morph_clustering.neurom_analysis, and run_analysis.
Status: candidate
"""
from importlib import import_module

from ._version import __version__

_REGION_NAMES = {
    "parse_swc",
    "NeuronTracer",
    "RegionAnalysisPerNeuron",
    "NeuronClassifier",
    "PopulationRegionAnalysis",
}
_ONE_NAMES = {"analyze_one"}
_SOURCE_NAMES = {"ensure_cached_swc"}
_CONFIG_NAMES = {"load_config"}
_NEUROM_NAMES = {
    "neurom_available": ("available",),
    "neurom_extract_features": ("extract_features",),
    "neurom_features_table": ("features_table",),
}


def __getattr__(name):
    if name in _REGION_NAMES:
        return getattr(import_module(".region_analysis", __name__), name)
    if name in _ONE_NAMES:
        return getattr(import_module(".run_analysis", __name__), name)
    if name in _SOURCE_NAMES:
        return getattr(import_module(".region_analysis.neuron_loader", __name__), name)
    if name in _CONFIG_NAMES:
        from .config import load
        return load
    if name in _NEUROM_NAMES:
        module = import_module(".morph_clustering.neurom_analysis", __name__)
        return getattr(module, _NEUROM_NAMES[name][0])
    raise AttributeError(name)


def __dir__():
    return sorted(
        set(globals())
        | _REGION_NAMES
        | _ONE_NAMES
        | _SOURCE_NAMES
        | _CONFIG_NAMES
        | set(_NEUROM_NAMES)
    )


__all__ = sorted(
    {"__version__"}
    | _REGION_NAMES
    | _ONE_NAMES
    | _SOURCE_NAMES
    | _CONFIG_NAMES
    | set(_NEUROM_NAMES)
)
