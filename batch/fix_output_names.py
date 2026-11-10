"""Normalize current VisPa batch output filenames and receipt paths.

Version: 1.21.7 (local/unreleased)
Last updated: 2026-11-09
Change history: ../CHANGELOG.md
Status: candidate

The command is dry-run by default. It renames only files referenced by each
animal's current process-log record; historical and unreferenced files remain
untouched.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from vispa.config import load, output_filename
from vispa.render_records import animal_receipt_path


_ROLE_PATTERNS = (
    ("Soma_Plot", re.compile(r"_Soma_Plot\.png$", re.IGNORECASE)),
    ("Context_Plot", re.compile(r"_Context_Plot\.png$", re.IGNORECASE)),
    ("Sagittal_Plot", re.compile(r"_Sagittal_Plot\.png$", re.IGNORECASE)),
    ("TrioPlot", re.compile(r"_TriPlot\.png$", re.IGNORECASE)),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True, default=str)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _folder_parts(folder: str) -> tuple[str, str]:
    parts = folder.split("_")
    neuron = parts[0]
    side = parts[1] if len(parts) > 1 and parts[1] in {"L", "R"} else None
    region = "_".join(parts[2:]) if side else "_".join(parts[1:])
    region = re.sub(r"[^A-Za-z0-9]+", "_", region).strip("_")
    if not region or region.casefold() == "unassigned":
        return neuron, "atlas_unavailable"
    return neuron, (f"atlas_{side}_{region}" if side else f"atlas_{region}")


def _classify(path: Path) -> tuple[str, str] | None:
    name = path.name
    for role, pattern in _ROLE_PATTERNS:
        if pattern.search(name):
            return role, ".png"
    if re.search(r"_SWC3D\.png$", name, flags=re.IGNORECASE):
        return "SWC3D", ".png"
    if re.search(r"_3D_SWC\.png$", name, flags=re.IGNORECASE):
        return "SWC3D", ".png"
    if re.search(r"_Soma\.nii\.gz$", name, flags=re.IGNORECASE):
        return "Soma", ".nii.gz"
    if re.search(r"_Soma\.nii$", name, flags=re.IGNORECASE):
        return "Soma", ".nii"
    return None


def plan_sample(output_root: Path, sample: str, template: str) -> dict:
    receipt_path = animal_receipt_path(output_root, sample)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    mappings = []
    seen = set()
    for neuron, slot in sorted((receipt.get("neurons") or {}).items()):
        current = (slot or {}).get("current") or {}
        outputs = current.get("outputs") or {}
        products = current.get("products") or {}
        referenced = [value.get("path") for value in outputs.values()
                      if isinstance(value, dict) and value.get("path")]
        referenced.extend(
            value.get("path") for value in (current.get("other_outputs") or {}).values()
            if isinstance(value, dict) and value.get("path"))
        swc = ((products.get("SWC3D") or {}).get("output") or {}).get("path")
        if swc:
            referenced.append(swc)
        for raw_path in referenced:
            source = Path(raw_path)
            if not source.is_file():
                continue
            classified = _classify(source)
            if classified is None:
                continue
            role, suffix = classified
            neuron_id = Path(neuron).stem
            folder_path = source.parent
            sample_root = output_root / sample
            while (folder_path.parent != sample_root and
                   not (folder_path.name == neuron_id or
                        re.match(rf"^{re.escape(neuron_id)}_[LR]_", folder_path.name))):
                folder_path = folder_path.parent
            folder = folder_path.name
            folder_neuron, region_source = _folder_parts(folder)
            if folder_neuron != neuron_id:
                raise ValueError(
                    f"Folder/neuron identity differs for {sample}: {folder} vs {neuron}")
            target = source.with_name(
                output_filename(sample=sample, neuron=neuron_id,
                                region_source=region_source, role=role,
                                template=template) + suffix)
            key = (source, target)
            if key in seen:
                continue
            seen.add(key)
            companions = []
            if suffix in {".nii", ".nii.gz"}:
                old_sidecar = source.with_name(source.name + ".json")
                if old_sidecar.is_file():
                    companions.append((old_sidecar, target.with_name(target.name + ".json")))
            elif role == "SWC3D":
                old_sidecar = source.with_suffix(".json")
                if old_sidecar.is_file():
                    companions.append((old_sidecar, target.with_suffix(".json")))
            mappings.append({
                "neuron_id": neuron,
                "source": source,
                "target": target,
                "role": role,
                "source_sha256": None,
                "status": ("unchanged" if source == target else
                           "conflict" if target.exists() and
                           _sha256(target) != _sha256(source)
                           else "planned"),
                "companions": companions,
            })
    return {"sample_id": sample, "receipt": receipt_path,
            "mappings": mappings,
            "conflicts": [item for item in mappings if item["status"] == "conflict"]}


def _rewrite_paths(value, replacements: dict[str, str]):
    if isinstance(value, str):
        for old, new in replacements.items():
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [_rewrite_paths(item, replacements) for item in value]
    if isinstance(value, dict):
        return {_rewrite_paths(key, replacements): _rewrite_paths(item, replacements)
                for key, item in value.items()}
    return value


def apply_sample(plan: dict) -> dict:
    if plan["conflicts"]:
        raise FileExistsError(f"Name conflicts prevent applying {plan['sample_id']}")
    replacements = {}
    renamed = []
    for item in plan["mappings"]:
        source, target = item["source"], item["target"]
        if source == target:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(target)
        digest = _sha256(source)
        source.rename(target)
        replacements[str(source)] = str(target)
        replacements[source.name] = target.name
        renamed.append({"source": str(source), "target": str(target),
                        "sha256": digest})
        for old_sidecar, new_sidecar in item["companions"]:
            if not old_sidecar.is_file() or new_sidecar.exists():
                raise FileExistsError(old_sidecar)
            old_sidecar.rename(new_sidecar)
            replacements[str(old_sidecar)] = str(new_sidecar)
            replacements[old_sidecar.name] = new_sidecar.name
            renamed.append({"source": str(old_sidecar), "target": str(new_sidecar),
                            "sha256": _sha256(new_sidecar)})
    for item in plan["mappings"]:
        for _old_sidecar, new_sidecar in item["companions"]:
            if new_sidecar.is_file():
                payload = json.loads(new_sidecar.read_text(encoding="utf-8"))
                _atomic_json(new_sidecar, _rewrite_paths(payload, replacements))
    for entry in renamed:
        entry["sha256"] = _sha256(Path(entry["target"]))
    receipt_path = plan["receipt"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt = _rewrite_paths(receipt, replacements)
    receipt.setdefault("filename_normalizations", []).append({
        "normalized_at_utc": datetime.now(timezone.utc).isoformat(),
        "mappings": renamed,
    })
    _atomic_json(receipt_path, receipt)
    return {"sample_id": plan["sample_id"], "renamed": renamed}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--sample", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    if bool(args.sample) == args.all:
        parser.error("Choose explicit --sample values or --all")
    config = load(args.config.resolve(strict=True))
    template = config["visual_toolkit"].get(
        "filename_template", "{sample}_{neuron}_{region_source}_{role}")
    root = args.output_root.expanduser().resolve()
    samples = args.sample or sorted(
        path.parent.name for path in root.glob("*/process_log.json"))
    plans = [plan_sample(root, sample, template) for sample in samples]
    result = {
        "schema": "vispa.batch_filename_fix.v1",
        "dry_run": not args.apply,
        "output_root": str(root),
        "template": template,
        "samples": plans,
        "applied": [apply_sample(plan) for plan in plans] if args.apply else [],
    }
    if args.report:
        _atomic_json(args.report, result)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    conflicts = [item for plan in plans for item in plan["conflicts"]]
    return 2 if conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
