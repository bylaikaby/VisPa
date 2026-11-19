"""Generate the VisPa and ReMAP function inventory and workflow chart.

Version: 0.1.4 (local/unreleased)
Last updated: 2026-11-19
Change history: ../../CHANGELOG.md
2026-11-19: make the single-monkey route sample-neutral.
2026-11-19: trace single- and multi-monkey analysis and the Insula Analysis Package.
2026-11-19: use a shared operator tree with file, callable and data nodes.
2026-11-19: show the verified operator workflows below the function inventory.
2026-11-19: build both PNG and Markdown from the active source modules.
"""
from __future__ import annotations

import ast
from importlib.util import find_spec
import io
import os
from pathlib import Path
import re
from urllib.parse import quote

VERSION = "0.1.4"

CORE_GROUPS = {
    "VisPa": (
        ("Desktop and settings", "Review, configure and check data",
         ("reviewer.py", "commands.py", "config.py", "readiness.py")),
        ("Data and anatomy", "Load sources, validate coordinates and inspect terminals",
         ("data_input_adaptor.py", "sources.py", "image_geometry.py", "swc_terminal_candidates.py")),
        ("Microscopy and 3D", "Soma, Context, Sagittal, TrioPlot, Brain View and montage",
         ("renderers/microscopy_panels.py", "derived_context.py",
          "renderers/swc_brain_view.py", "renderers/brain_volume_montage.py")),
        ("Batch review", "Prepare jobs, render outputs and record provenance",
         ("review_bulk_dialog.py", "review_bulk_prepare.py", "review_bulk_render.py", "render_records.py")),
        ("FNT and cohort progress", "Prepare native FNT, launch Tracer and show composition",
         ("fnt.py", "fnt_tracer_launcher.py", "cohort_progress.py")),
        ("Operator support", "Public example, updates, desktop shortcuts and this overview",
         ("public_example.py", "updates.py", "shortcuts.py", "function_overview.py")),
    ),
    "ReMAP": (
        ("Regional measurements", "One-neuron or population analysis and projection tables",
         ("cli.py", "run_analysis.py", "population_operator.py", "region_analysis/neuron_table.py")),
        ("Atlas and SWC preparation", "Load registered SWCs, resolve atlas and read DS00 selection",
         ("atlas_profile.py", "ds_normalisation/ds00_selection.py",
          "ds_normalisation/coordinates.py", "region_analysis/neuron_loader.py")),
        ("FNT production and analysis", "Prepare FNT distances and compare saved candidates",
         ("morph_clustering/fnt_pipeline.py", "morph_clustering/clustering_validation.py",
          "morph_clustering/compare.py", "morph_clustering/compare_flip.py")),
        ("Morphology and hierarchy review", "Check features, inspect scores and render candidate hierarchies",
         ("morph_clustering/neurom_analysis.py", "morph_clustering/score_plot.py",
          "morph_clustering/review_profile.py", "morph_clustering/review_plot.py")),
        ("Tables and cohort progress", "Export source tables, add candidate assignments and summarize composition",
         ("table.py", "morph_clustering/clustered_table.py", "cohort_progress.py")),
    ),
}

OUTPUT_NAMES = ("vispa_function_overview.md", "vispa_function_overview.png")
TAG = re.compile(r"(?m)^\s*#?\s*Version:\s*([^\r\n]+)")

# Each stage declares its type, label, second line and incoming edge label.
WORKFLOWS = (
    ("SWC Brain View", "vispa gui", ("VisPa",), (
        ("data", "Selected sample and neuron", "Settings select the SWC and mesh", ""),
        ("file", "reviewer.py", "_render_swc3d()", "reads selection"),
        ("file", "renderers/swc_brain_view.py", "render_configured_snapshot()", "calls"),
        ("data", "Brain View snapshot", "Preview or saved PNG + receipt", "writes"),
    )),
    ("Bulk review", "Desktop action or python -m", ("VisPa",), (
        ("data", "Review roster and settings", "Sample IDs · neuron IDs · panels", ""),
        ("file", "review_bulk_prepare.py", "prepare_jobs()", "resolves"),
        ("data", "Prepared jobs JSON", "Inputs and output plan", "writes"),
        ("file", "review_bulk_render.py", "main()", "reads jobs"),
        ("data", "Review panels", "PNGs + render records", "writes"),
    )),
    ("Cohort composition", "Desktop or vispa progress", ("VisPa", "ReMAP"), (
        ("external", "Progress Manager export", "CSV + optional matching\nper-neuron cohort receipt", ""),
        ("file", "VisPa · cohort_progress.py", "build_report()", "receives paths"),
        ("file", "ReMAP · cohort_progress.py", "build_report()", "calls"),
        ("data", "Cohort report", "Desktop preview or PNG + receipt", "returns"),
    )),
)

PAPER_METHODS = (
    ("PFC reference replay", "Published SWCs · atlases · tables", (
        ("file", "replay_pfc_projection.py", "main()", "measures"),
        ("data", "Published reference", "Reference projections and provenance", "writes"),
    )),
    ("Insula projection measurements", "ARM L6 · original template SWCs · roster", (
        ("file", "transfer_figure2a.py", "main()", "measures"),
        ("data", "Regional axon lengths", "Per-neuron lengths + cohort receipt", "writes"),
        ("file", "render_figure2a.py", "main()", "renders with saved order"),
        ("data", "Bilateral axon matrix", "Figure 2A adaptation + receipt", "writes"),
    )),
    ("Soma flat maps", "Scoped soma coordinates · reference mesh", (
        ("file", "replay_gou_flatmap.jl", "main(args)", "projects soma points"),
        ("file", "render_insula_flatmap_legacy.py", "main()", "reads UVW table"),
        ("data", "Labeled flat maps", "309 insula or 411 with surroundings", "writes"),
    )),
    ("3D morphology", "Original SWCs · atlas region meshes", (
        ("file", "render_neuronview_atlas_stereo.py", "main()", "renders"),
        ("data", "Atlas stereo views", "Trace and region mesh context", "writes"),
    )),
    ("Functional evidence", "Table S2 · atlas masks · insula SWCs", (
        ("file", "audit_gou_function_crosswalk.py", "main()", "tests correspondence"),
        ("data", "Area and term coverage", "Measured coverage and evidence gaps", "writes"),
    )),
)

WORKFLOW_KEY = (
    "Blue frames are files. Green nodes are functions. Gray nodes are data. "
    "Solid arrows show calls; dashed arrows show data transfers."
)

WORKFLOW_COLORS = {
    "file": ("#F4F8FF", "#6186B5"),
    "function": ("#E8F5EE", "#23845B"),
    "data": ("#F1F5F9", "#64748B"),
    "external": ("#FFFFFF", "#64748B"),
    "candidate": ("#FFF5DD", "#B7791F"),
    "route": ("#FFFFFF", "#64748B"),
}


def configure_parser(parser):
    parser.add_argument("--version", action="version", version=f"VisPa Function Overview {VERSION}")
    parser.add_argument("--output-dir", type=Path, required=True, help="new directory for the PNG and Markdown")
    parser.add_argument("--dry-run", action="store_true", help="inventory source and print output paths without writing")


def declared_version(path):
    """Read explicit version metadata and fall back to package tracking when absent."""
    match = TAG.search(path.read_text(encoding="utf-8-sig"))
    return match[1].strip() if match else None


def _public_symbols(path):
    syntax = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    kinds = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    return [node.name for node in syntax.body if isinstance(node, kinds) and not node.name.startswith("_")]


def _commands(path, owner):
    """Read argparse registrations without opening datasets or initializing the GUI."""
    syntax = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    commands = []
    calls = [call for call in ast.walk(syntax) if isinstance(call, ast.Call)
             and isinstance(call.func, ast.Attribute) and call.func.attr == "add_parser"]
    for call in sorted(calls, key=lambda node: node.lineno):
        name = ast.literal_eval(call.args[0])
        prefix = f"{owner} tuning" if getattr(call.func.value, "id", None) == "tuning_actions" else owner
        values = {kw.arg: kw.value for kw in call.keywords}
        aliases = ast.literal_eval(values["aliases"]) if "aliases" in values else []
        help_text = ast.literal_eval(values["help"])
        commands.append((f"{prefix} {name}", aliases, help_text))
    return commands


def build_overview():
    """Return a source-bound inventory of the coupled VisPa and ReMAP packages."""
    vispa = Path(__file__).resolve().parent
    spec = find_spec("remap")
    roots = {"VisPa": vispa, "ReMAP": Path(spec.origin).resolve().parent if spec and spec.origin else None}
    packages = {}
    for owner, root in roots.items():
        if root is None:
            packages[owner] = None
            continue
        version_path = root / "_version.py"
        syntax = ast.parse(version_path.read_text(encoding="utf-8-sig"))
        version = next(ast.literal_eval(stmt.value) for stmt in syntax.body if isinstance(stmt, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "__version__" for t in stmt.targets))
        scripts = {path.relative_to(root).as_posix(): declared_version(path) for path in sorted(root.rglob("*.py"))
                   if path.name != "__init__.py"}
        absent = {name for _, _, names in CORE_GROUPS[owner] for name in names if name not in scripts}
        if absent:
            raise ValueError(f"{owner} core modules missing from the active source: {', '.join(sorted(absent))}")
        router = "commands.py" if owner == "VisPa" else "cli.py"
        packages[owner] = {"root": root, "version": version, "scripts": scripts,
                           "symbols": {name: _public_symbols(root / name) for name in scripts},
                           "commands": _commands(root / router, owner.lower()), "router": router}
    checkout = vispa.parents[1]
    paths = [checkout / "run_vispa.py", *sorted((checkout / "batch").glob("*.py")),
             *sorted((checkout / "scripts").glob("*.ps1"))]
    workspace = {p: declared_version(p) for p in paths
                 if p.is_file() and p.name != "__init__.py" and not p.name.startswith("test_")}
    return packages, workspace


def _source_link(path, label, destination):
    try:
        target = quote(Path(os.path.relpath(path, destination)).as_posix(), safe="/._-")
    except ValueError:
        return f"{label} (see package source)"
    return f"[\x60{label}\x60]({target})"


def _label(version):
    return version.split()[0] if version else "package-tracked"


def _workflow_graph(packages):
    """Define the displayed operators and their file handoffs once for both renderers."""
    nodes, edges = {}, []

    def add(key, role, label, detail, column, row, width=.92):
        nodes[key] = (role, label, detail, column, row, width)

    def join(source, target, label=""):
        edges.append((source, target, label))

    def chain(previous, stages, column, start):
        for row, (role, label, detail, edge) in enumerate(stages, start):
            key = f"column{column:g}row{row}".replace(".", "_")
            add(key, role, label, detail, column, row)
            join(previous, key, edge)
            previous = key
        return previous

    add("overview", "route", "Operator workflows", "", 3, 0, 1.45)
    remap = packages["ReMAP"] is not None
    add("VisPa", "route", "VisPa", "", 1 if remap else 3, 1)
    join("overview", "VisPa")
    routes = [route for route in WORKFLOWS if all(packages[owner] is not None for owner in route[2])]
    for index, (title, entry, _, stages) in enumerate(routes):
        column = index if remap else 2 + 2 * index
        key = f"vispa{index}"
        add(key, "route", title, entry, column, 2)
        join("VisPa", key)
        chain(key, stages, column, 3)

    if not remap:
        return nodes, edges

    add("ReMAP", "route", "ReMAP", "", 4.5, 1)
    join("overview", "ReMAP")
    for scope, title, example, source, binding, column in (
        ("single", "Single monkey", "Any configured sample · saved inputs or new run",
         "Exact sample/neuron IDs and declared coordinates", "One sample workbook or explicit bindings", 3.5),
        ("multi", "Multiple monkeys", "Nine monkeys · 490 exploratory candidates",
         "Cohort ledger · composite IDs · common template", "Bind per-sample workbooks by sample and animal", 5.5),
    ):
        add(scope, "route", title, example, column, 2, 1.84)
        join("ReMAP", scope)
        spec = scope + "inputs"
        add(spec, "data", "Selected SWCs and scope", source, column, 3, 1.74)
        join(scope, spec)
        region = chain(spec, (
            ("file", "population_operator.py", "plan_population()\nrun_population()", "regions per sample"),
            ("file", "region_analysis/neuron_table.py", "PopulationRegionAnalysis\n.process() / .save_all()", "calls"),
            ("data", "Regional table inputs", "Summary + projection sheets", "writes"),
        ), column - .5, 4)
        scores = chain(spec, (
            ("file", "fnt_pipeline.py", "validate_settings()\nBounded check and frozen plan", "FNT settings"),
            ("file", "fnt_pipeline.py", "run_pipeline()\nConvert · decimate · join · score", "validated plan"),
            ("data", "Saved FNT inputs", "Joined FNT · distance TSV · receipt", "writes"),
        ), column + .5, 4)
        review = scope + "review"
        add(review, "file", "review_plot.py", "main() / load_tables() · fit review profile\n" + binding,
            column, 7, 1.84)
        join(region, review, "match workbook IDs")
        join(scores, review, "match score order")
        result = scope + "result"
        detail = "Candidate hierarchy · projection PNG · assignments"
        if scope == "multi":
            detail += "\nParent 490 · optional ARM L6 display of 309"
        add(result, "candidate", "Clustering and projection review", detail, column, 8, 1.84)
        join(review, result, "writes")
        table = scope + "table"
        table_column = 3.35 if scope == "single" else 6.0
        add(table, "file", "clustered_table.py", "evolve()" if scope == "single" else "assemble_cohort() / evolve()",
            table_column, 9, 1.1)
        join(result, table, "assignments + source tables")
        add(scope + "workbook", "candidate", "neuron_table_clustered", "Original rows + candidate labels",
            table_column, 10, 1.1)
        join(table, scope + "workbook", "writes")

    add("paper", "route", "Insula Analysis Package", "Pinned study drivers", 4.65, 11, 1.75)
    # The package reads the study's frozen cohort inputs and optional hierarchy order.
    # It can be replayed without making a clustered workbook first.
    add("study_inputs", "data", "Frozen study inputs", "Insula roster · template SWCs\nSaved order when used",
        4.65, 9, 1.35)
    join("multiresult", "study_inputs", "saved order when used")
    join("study_inputs", "paper")
    for index, (title, inputs, stages) in enumerate(PAPER_METHODS):
        column = index * 1.39 + .22
        key = f"paper{index}"
        add(key, "external" if index == 0 else "data", title, inputs, column, 12, 1.29)
        join("paper", key)
        chain(key, stages, column, 13)
    return nodes, edges


def mermaid_chart(packages):
    """Render one operator tree with labeled calls and data transfers."""
    nodes, edges = _workflow_graph(packages)
    lines = [
        '%%{init: {"theme":"base","themeVariables":{"edgeLabelBackground":"#FFFFFF",'
        '"lineColor":"#4B606C"},"flowchart":{"curve":"stepAfter","rankSpacing":30}}}%%',
        'flowchart TB',
    ]
    for key, (role, label, detail, *_) in nodes.items():
        caption = "<br/>".join(detail.splitlines())
        text = "<br/>".join(item for item in (label, caption) if item)
        if role == "file":
            fill, stroke = WORKFLOW_COLORS[role]
            # Attach to the frame so arrows clear the filename above its callable.
            lines.extend([f'  subgraph {key}["{label}"]',
                          f'    {key}fn(["{caption}"]):::function', "  end",
                          f"  style {key} fill:{fill},stroke:{stroke},color:#243C5A"])
        elif role == "route":
            lines.append(f'  {key}["{text}"]:::route')
        else:
            lines.append(f'  {key}[/"{text}"/]:::{role}')
    for source, target, edge in edges:
        # Keep the paper-method branch rail below the clustered-workbook outputs.
        connector = '-' * (2 + nodes[target][4] - nodes[source][4]) if not edge else f'-. "{edge}" .->'
        if edge == "calls":
            connector = '-->|"calls"|'
        lines.append(f"  {source} {connector} {target}")
    for role, (fill, stroke) in WORKFLOW_COLORS.items():
        if role == "file":
            continue
        dash = ",stroke-dasharray:5 3" if role in ("external", "candidate") else ""
        lines.append(f"  classDef {role} fill:{fill},stroke:{stroke},color:#192C38{dash}")
    return "\n".join(lines)


def make_markdown(packages, workspace, destination):
    lines = ["# VisPa Function Overview", "", f"Overview generator {VERSION}.",
             "The inventory maps core responsibilities to source scripts and versions.",
             "", "![Core functions and workflows](vispa_function_overview.png)", ""]
    for owner, pack in packages.items():
        lines += [f"## {owner}", ""]
        if pack is None:
            lines += ["ReMAP source was unavailable in the active Python environment.", ""]
            continue
        lines += [f"Active package version \x60{pack['version']}\x60.",
                  "The module column reports each declared source version. Package-tracked files have no separate source tag.",
                  "", "| Core responsibility | Source scripts and declared versions |",
                  "| --- | --- |"]
        root = pack["root"]
        for name, use, modules in CORE_GROUPS[owner]:
            files = " · ".join(f"{_source_link(root / f, f, destination)} ({_label(pack['scripts'][f])})" for f in modules)
            lines.append(f"| **{name}**. {use} | {files} |")
        router = _source_link(root / pack["router"], pack["router"], destination)
        lines += ["", f"### Registered commands", "", f"Command registration lives in {router}.",
                  "", "| Command | Purpose |", "| --- | --- |"]
        for name, aliases, help_text in pack["commands"]:
            alias = f" (aliases {', '.join(aliases)})" if aliases else ""
            lines.append(f"| \x60{name}\x60{alias} | {help_text.replace('|', '/')} |")
        lines += ["", "### Source version and function index", "",
                  "Public top-level definitions are read from source. The registered commands above describe operator entry points.",
                  "", "| Source module | Declared version | Public functions and classes |", "| --- | --- | --- |"]
        for name, version in pack["scripts"].items():
            symbols = ", ".join(f"`{symbol}`" for symbol in pack["symbols"][name]) or "—"
            lines.append(f"| {_source_link(root / name, name, destination)} | {version or 'Package-tracked'} | {symbols} |")
        lines.append("")
    if workspace:
        lines += ["## Checkout operators", "", "| Script | Declared version |", "| --- | --- |"]
        for path, version in workspace.items():
            label = path.name if path.name == "run_vispa.py" else f"{path.parent.name}/{path.name}"
            lines.append(f"| {_source_link(path, label, destination)} | {version or 'Package-tracked'} |")
        lines.append("")
    lines += ["## Workflow", "",
              "Follow the branch for your operator from top to bottom. " + WORKFLOW_KEY,
              "Bulk review uses `python -m vispa.review_bulk_prepare` and `python -m vispa.review_bulk_render`.",
              "", "\x60\x60\x60mermaid", mermaid_chart(packages), "\x60\x60\x60", ""]
    if packages["ReMAP"] is not None:
        lines += _workflow_notes(packages["VisPa"]["root"], destination)
    return "\n".join(lines)


def _workflow_notes(vispa_root, destination):
    lines = [
        "### Run the ReMAP branches", "",
        "| Scope | Inputs and checks | Entry points and outputs |",
        "| --- | --- | --- |",
        "| Single monkey | Supply any configured sample ID, exact neuron IDs, declared SWC coordinates and the matching regional workbook. | Replay saved FNT inputs or produce scores for a new bounded run. With sample-prefixed FNT identities, pass the source workbook to `review_plot --source-workbook` to evolve a copy alongside the figures. |",
        "| Multiple monkeys | Bind exact sample, animal and neuron identities in one declared common template and unit system. Check a bounded case before running the complete cohort. | Produce or reuse complete FNT scores and per-sample projection tables. The saved 490-neuron reflection plan uses Xmid 32000 and decimation distance/area 5000/5000. The matched fold remains a comparator. |",
        "| Atlas insula display | Match the 309 ARM L6 soma roster to the parent cohort. | Use `review_plot --alternative-style neuron_projection --atlas-insula-receipt ...`. The display inherits the parent tree, candidate labels, and projection scale. |",
        "",
        "The bounded `remap fnt-pipeline` command can cluster in the same run with `--cluster`. "
        "Bounded `remap fnt-analyze` can reuse a producer receipt. Both public commands cap the case count at 32. "
        "The full-cohort replay follows the saved study workflow. Sample 251637 is a historical example with a 212-neuron raw audit and a separate 260-neuron saved review.",
        "",
        "For either scope, run `python -m remap.morph_clustering.review_plot --profile PROFILE --distance DISTANCE --joined-fnt JOINED --tables TABLES --output NEW_DIR --dry-run` to check the saved inputs. The study workbook evolves by adding named candidate assignments to preserved source rows.",
        "",
    ]
    for parent in vispa_root.parents:
        guide = parent / "work" / "remap_clustering_all_monkeys_20261117" / "README.md"
        if guide.is_file():
            link = _source_link(guide, "Insula Analysis Package operator guide", destination)
            lines += [f"The {link} records the pinned drivers, commands, outputs and panel prerequisites.", ""]
            break
    return lines


def draw_workflow(ax, packages):
    """Place the same workflow graph below the core function chart."""
    from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle

    nodes, edges = _workflow_graph(packages)
    last_row = max(node[4] for node in nodes.values())
    ax.set_xlim(-.65, 6.65)
    ax.set_ylim(last_row + .59, -1.75)
    ax.set_axis_off()
    ink, muted = "#192c38", "#4b606c"
    ax.plot([-.35, 6.35], [-1.54, -1.54], color="#dce5e9", lw=.8)
    ax.text(-.35, -1.37, "Workflow", fontsize=21, color=ink, weight="bold", va="top")
    ax.text(-.35, -.90, WORKFLOW_KEY, fontsize=11, color=muted, va="top")
    height = .61
    for source, target, label in edges:
        x0, y0 = nodes[source][3:5]
        x1, y1 = nodes[target][3:5]
        start, end = y0 + height/2, y1 - height/2
        bend = (start + end)/2
        solid = not label or label == "calls"
        ax.plot([x0, x0, x1, x1], [start, bend, bend, end],
                color=muted, lw=.85, linestyle="-" if solid else "--", zorder=1)
        if label:
            ax.annotate("", xy=(x1, end), xytext=(x1, bend),
                        arrowprops={"arrowstyle": "-|>", "color": muted, "lw": .7,
                                    "mutation_scale": 9, "shrinkA": 2, "shrinkB": 1})
            if x0 == x1:
                label_x, label_y, align = x1 + .045, bend, "left"
            else:
                label_x, label_y, align = (x0 + x1)/2, bend - .035, "center"
            ax.text(label_x, label_y, label, fontsize=8.5, color=muted, ha=align, va="center",
                    bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.4}, zorder=2)

    for role, label, detail, x, y, width in nodes.values():
        left, right = x - width/2, x + width/2
        top, bottom = y - height/2, y + height/2
        fill, stroke = WORKFLOW_COLORS[role]
        if role in ("file", "route"):
            shape = Rectangle((left, top), width, height, facecolor=fill, edgecolor=stroke, lw=.9)
        else:
            skew = .045
            shape = Polygon([(left, bottom), (left + skew, top), (right, top), (right - skew, bottom)],
                            facecolor=fill, edgecolor=stroke, lw=.9,
                            linestyle="--" if role in ("external", "candidate") else "-")
        shape.set_zorder(3)
        ax.add_patch(shape)
        if role == "file":
            fn_fill, fn_stroke = WORKFLOW_COLORS["function"]
            ax.add_patch(FancyBboxPatch((left + .055, top + .22), width - .11, .32,
                                       boxstyle="round,pad=0,rounding_size=.095",
                                       facecolor=fn_fill, edgecolor=fn_stroke, lw=.8, zorder=4))
        label_y = y - .17 if role == "file" else y - .10 if detail else y
        detail_y = y + .075 if role == "file" else y + .11
        ax.text(x, label_y, label, fontsize=9.8 if role == "file" else 11.5,
                color=ink, weight="normal" if role == "file" else "bold",
                ha="center", va="center", zorder=5)
        if detail:
            ax.text(x, detail_y, detail, fontsize=9.2, color=ink, ha="center", va="center",
                    family="DejaVu Sans Mono" if role == "file" else None, linespacing=1, zorder=5)


def make_png(packages, workspace):
    """Render the core module groups using the same inventory as the Markdown."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.patches import Rectangle

    workflow_height = 18 if packages["ReMAP"] is not None else 9
    total_height = 17 + workflow_height
    fig = Figure(figsize=(23, total_height), facecolor="white")
    FigureCanvasAgg(fig)
    workflow_fraction = workflow_height/total_height
    ax = fig.add_axes((0, workflow_fraction, 1, 1 - workflow_fraction))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_axis_off()
    ink, muted, blue = "#192c38", "#4b606c", "#6186b5"
    ax.text(.042, .971, "VisPa Function Overview", fontsize=26, color=ink, weight="bold", va="top")
    ax.text(.042, .935, "Core responsibilities and source versions", fontsize=13, color=muted, va="top")
    for index, (owner, groups) in enumerate(CORE_GROUPS.items()):
        x = .042 + index * .477
        pack = packages[owner]
        if pack is None:
            ax.text(x, .891, "ReMAP source unavailable", fontsize=15, color=muted, va="top")
            continue
        version = pack["version"]
        header_color = "#fff5dd" if ".dev" in version else "#f4f8ff"
        ax.add_patch(Rectangle((x, .849), .438, .044, facecolor=header_color, edgecolor="#a7b4bd", linewidth=.8))
        ax.text(x + .014, .871, f"{owner}  {version}", fontsize=17, color=ink, weight="bold", va="center")
        top = .824
        for title, use, scripts in groups:
            height = .054 + len(scripts) * .015
            ax.add_patch(Rectangle((x, top - height), .438, height, facecolor="#f4f8ff",
                                   edgecolor=blue, linewidth=.55))
            ax.text(x + .014, top - .013, title, fontsize=13.5, color=ink, weight="bold", va="top")
            ax.text(x + .014, top - .032, use, fontsize=9.5, color=muted, va="top")
            for i, name in enumerate(scripts):
                y = top - .051 - i * .015
                ax.text(x + .014, y, name, fontsize=9.5, family="DejaVu Sans Mono", color=ink, va="top")
                ax.text(x + .424, y, _label(pack["scripts"][name]), fontsize=9.5, color=muted, va="top", ha="right")
            top -= height + .013
        if owner == "ReMAP" and workspace:
            height = .037 + len(workspace) * .0145
            ax.add_patch(Rectangle((x, top - height), .438, height, facecolor="#f8fafb",
                                   edgecolor="#a7b4bd", linewidth=.55))
            ax.text(x + .014, top - .011, "Checkout operators", fontsize=13.5, color=ink, weight="bold", va="top")
            for i, (path, version) in enumerate(workspace.items()):
                name = path.name if path.name == "run_vispa.py" else f"{path.parent.name}/{path.name}"
                y = top - .032 - i * .0145
                ax.text(x + .014, y, name, fontsize=9.5, family="DejaVu Sans Mono", color=ink, va="top")
                ax.text(x + .424, y, _label(version), fontsize=9.5, color=muted, va="top", ha="right")
    draw_workflow(fig.add_axes((0, 0, 1, workflow_fraction)), packages)
    output = io.BytesIO()
    fig.savefig(output, format="png", dpi=155)
    return output.getvalue()


def export_overview(output_dir, *, dry_run=False):
    """Write the PNG and Markdown together under a fresh output directory."""
    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"Choose a new overview directory: {destination}")
    packages, workspace = build_overview()
    files = [destination / name for name in OUTPUT_NAMES]
    result = {
        "version": VERSION, "dry_run": dry_run,
        "packages": {name: {"version": p["version"], "scripts": len(p["scripts"]), "commands": len(p["commands"])}
                     if p is not None else None for name, p in packages.items()},
        "checkout_operators": len(workspace),
        "outputs": [str(p) for p in files],
    }
    if dry_run:
        return result
    contents = (make_markdown(packages, workspace, destination).encode("utf-8"), make_png(packages, workspace))
    destination.mkdir(parents=True, exist_ok=False)
    created = []
    try:
        for path, content in zip(files, contents, strict=True):
            with path.open("xb") as stream:
                created.append(path)
                stream.write(content)
    except OSError:
        for path in created:
            path.unlink()
        if not any(destination.iterdir()):
            destination.rmdir()
        raise
    return result
