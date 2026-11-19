"""ReMAP extracted region analysis.

Importing this package does not load the neuron workbook.
Public names are loaded on first access.

Version: 0.1.0.dev28 (local/unreleased)
Last updated: 2026-11-10
Change history:
- 2026-11-10: Public names load from neuron_table, neuron_loader, neuron_swc, hierarchy, and overview_plots.
Status: candidate
"""
from importlib import import_module

_EXPORTS = {
    "parse_swc": (".neuron_table", "parse_swc"),
    "PopulationRegionAnalysis": (".neuron_table", "PopulationRegionAnalysis"),
    "RegionAnalysisPerNeuron": (".neuron_table", "RegionAnalysisPerNeuron"),
    "ensure_cached_swc": (".neuron_loader", "ensure_cached_swc"),
    "NeuronTracer": (".neuron_swc", "NeuronTracer"),
    "RegionHierarchy": (".hierarchy", "RegionHierarchy"),
    "add_soma_hierarchy_column": (".hierarchy", "add_soma_hierarchy_column"),
    "add_projection_length_hierarchy": (".hierarchy", "add_projection_length_hierarchy"),
    "add_projection_hierarchy": (".hierarchy", "add_projection_hierarchy"),
    "extract_soma_level": (".hierarchy", "extract_soma_level"),
    "resolve_to_level": (".hierarchy", "resolve_to_level"),
    "HierarchyTable": (".hierarchy", "HierarchyTable"),
    "NeuronClassifier": (".neuron_table", "NeuronClassifier"),
    "OutputManager": (".neuron_table", "OutputManager"),
    "LateralityParser": (".neuron_table", "LateralityParser"),
    "add_laterality_columns": (".neuron_table", "add_laterality_columns"),
    "load_processed_df": (".neuron_table", "load_processed_df"),
    "parse_terminal_regions": (".neuron_table", "parse_terminal_regions"),
    "plot_soma_distribution_df": (".overview_plots", "plot_soma_distribution_df"),
    "plot_type_distribution_df": (".overview_plots", "plot_type_distribution_df"),
    "plot_terminal_distribution_df": (".overview_plots", "plot_terminal_distribution_df"),
    "plot_projection_sites_count_df": (".overview_plots", "plot_projection_sites_count_df"),
    "plot_region_distribution": (".overview_plots", "plot_region_distribution"),
    "plot_laterality_summary_df": (".overview_plots", "plot_laterality_summary_df"),
    "plot_neuron_projections": (".overview_plots", "plot_neuron_projections"),
}


def __getattr__(name):
    spec = _EXPORTS.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = spec
    return getattr(import_module(module_name, __name__), attr)


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))


__all__ = sorted(_EXPORTS)
