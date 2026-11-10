"""One animal-level history and verified figure cache for GUI and bulk review.

Version: 1.21.7 (local/unreleased)
Last updated: 2026-11-08
Change history: ../../CHANGELOG.md
Status: candidate
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .batch_run_lock import exclusive_batch


_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,80}\Z")
SCHEMA = "vispa.review.animal.v1"


def separate_plot_output_dir(neuron_root, config: dict) -> Path:
    """Route individual review PNGs using the saved profile setting."""
    if not isinstance(config, dict):
        raise TypeError("config must be a loaded mapping")
    from .config import validate_plot_subfolder
    folder = validate_plot_subfolder(
        (config.get("visual_toolkit") or {}).get("separate_plot_subfolder", ""))
    root = Path(neuron_root)
    return root / folder if folder else root


def animal_receipt_path(output_root, sample: str) -> Path:
    """Return the sole receipt path for a new flat-layout animal."""
    if not isinstance(sample, str) or not _TOKEN.fullmatch(sample):
        raise ValueError("sample must be one path-safe identifier")
    return Path(output_root).expanduser().resolve() / sample / "process_log.json"


def load_animal_receipt(path, sample: str) -> dict:
    path = Path(path)
    if not path.is_file():
        return {"schema": SCHEMA, "sample_id": sample, "current_batch": None,
                "batches": [], "neurons": {}}
    record = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(record, dict) or record.get("schema") != SCHEMA or
            record.get("sample_id") != sample or
            not isinstance(record.get("neurons"), dict) or
            not isinstance(record.get("batches"), list)):
        raise ValueError("animal receipt schema or sample differs")
    return record


def _write_atomic(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _new_batch(previous, batch) -> bool:
    return (previous is not None and
            (previous.get("attempt_id") != batch.get("attempt_id")
             if batch.get("attempt_id") is not None else
             previous.get("jobs_sha256") != batch.get("jobs_sha256")))


def record_neuron_output(path, sample: str, neuron: str, record: dict, *, batch=None) -> dict:
    """Append a neuron revision to one animal receipt, retaining prior history."""
    if not isinstance(neuron, str) or not re.fullmatch(r"[A-Za-z0-9_-]+\.swc", neuron):
        raise ValueError("neuron must be one SWC filename")
    path = Path(path)
    with exclusive_batch(path.with_suffix(".lock")):
        animal = load_animal_receipt(path, sample)
        slot = animal["neurons"].setdefault(neuron, {"current": None, "history": []})
        prior = slot.get("current")
        if prior is not None and prior.get("products") and "products" not in record:
            record = {**record, "products": prior["products"]}
        if prior is not None and prior != record:
            slot.setdefault("history", []).append(prior)
        slot["current"] = record
        if batch is not None:
            previous = animal.get("current_batch")
            if _new_batch(previous, batch):
                animal["batches"].append(previous)
            animal["current_batch"] = batch
        _write_atomic(path, animal)
    return animal


def record_neuron_product(path, sample: str, neuron: str,
                          product_name: str, product_record: dict) -> dict:
    """Append one ancillary product without replacing four-panel review state."""
    if not isinstance(neuron, str) or not re.fullmatch(r"[A-Za-z0-9_-]+\.swc", neuron):
        raise ValueError("neuron must be one SWC filename")
    if not isinstance(product_name, str) or not _TOKEN.fullmatch(product_name):
        raise ValueError("product_name must be one path-safe key")
    if not isinstance(product_record, dict):
        raise ValueError("product_record must be a mapping")
    path = Path(path)
    with exclusive_batch(path.with_suffix(".lock")):
        animal = load_animal_receipt(path, sample)
        slot = animal["neurons"].setdefault(neuron, {"current": None, "history": []})
        previous = slot.get("current")
        current = dict(previous) if previous is not None else {
            "sample_id": sample, "neuron_id": neuron, "outputs": {},
            "status": "partial_or_failed", "errors": [],
        }
        products = dict(current.get("products") or {})
        products[product_name] = product_record
        current["products"] = products
        if previous is not None and previous != current:
            slot.setdefault("history", []).append(previous)
        slot["current"] = current
        _write_atomic(path, animal)
    return animal


def update_animal_batch(path, sample: str, batch: dict) -> dict:
    """Persist the latest batch progress without creating another receipt."""
    path = Path(path)
    with exclusive_batch(path.with_suffix(".lock")):
        animal = load_animal_receipt(path, sample)
        previous = animal.get("current_batch")
        if _new_batch(previous, batch):
            animal["batches"].append(previous)
        animal["current_batch"] = batch
        _write_atomic(path, animal)
    return animal


def verified_neuron_record(path, sample: str, neuron: str, expected: dict,
                           *, expected_outputs=None,
                           expected_products=None) -> dict | None:
    """Return a complete current result only when inputs and PNG bytes still match."""
    try:
        animal = load_animal_receipt(path, sample)
        record = animal["neurons"][neuron]["current"]
        required_outputs = set(expected_outputs or {
            "Soma", "Context", "Sagittal", "TrioPlot"})
        required_products = set(expected_products or ())
        if (record.get("status") != "rendered_candidate" or record.get("errors") or
                any(record.get(key) != value for key, value in expected.items()) or
                set(record.get("outputs") or {}) != required_outputs or
                set(record.get("products") or {}) != required_products):
            return None
        from PIL import Image
        outputs = dict(record["outputs"])
        for product_name in required_products:
            product = (record.get("products") or {}).get(product_name) or {}
            output = product.get("output")
            if not isinstance(output, dict):
                return None
            outputs[product_name] = output
        folder = Path(record["output_dir"]).resolve(strict=True)
        seen = set()
        for output in outputs.values():
            candidate = Path(output["path"]).resolve(strict=True)
            if (not candidate.is_relative_to(folder) or candidate in seen or
                    not candidate.stat().st_size):
                return None
            seen.add(candidate)
            digest = hashlib.sha256()
            with candidate.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != output["sha256"]:
                return None
            with Image.open(candidate) as image:
                if image.format != "PNG":
                    return None
                image.verify()
            with Image.open(candidate) as image:
                image.load()
        return record
    except (OSError, ValueError, KeyError, TypeError):
        return None
