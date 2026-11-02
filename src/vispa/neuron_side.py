"""Exact-identity neuron laterality from a declared per-sample FULL workbook.

Version: 1.12.0.dev4 (local/unreleased)
Last updated: 2026-11-02
Change history: ../../../CHANGELOG.md
The workbook's recorded side is distinct from a portal region code or atlas mesh side.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import hashlib
import re
from zipfile import BadZipFile


def lookup_neuron_side(root: str | Path | None, sample_id: str, neuron_id: str) -> dict:
    """Return a side only for one unambiguous Summary identity and consistent region.

    Unknown results carry a reason. The source is read only and hashed before parse;
    a changed file during the read is rejected. No coordinate-frame inference occurs.
    """
    result = {"status": "unknown", "side": None, "reason": "", "source": None}
    if not root:
        result["reason"] = "sources.neuron_tables.root is not configured"
        return result
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sample_id or ""):
        result["reason"] = "invalid sample identity"
        return result
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.swc", neuron_id or ""):
        result["reason"] = "invalid exact neuron identity"
        return result
    path = Path(root).expanduser().resolve() / f"{sample_id}_FULL.xlsx"
    if not path.is_file():
        result["reason"] = "per-sample FULL workbook is unavailable"
        return result
    try:
        before = path.stat()
        if before.st_size > 64 * 1024 * 1024:
            result["reason"] = "FULL workbook exceeds 64 MiB limit"
            return result
        payload = path.read_bytes()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            result["reason"] = "FULL workbook changed during read"
            return result
        digest = hashlib.sha256(payload).hexdigest()
        from openpyxl import load_workbook
        workbook = load_workbook(BytesIO(payload), read_only=True, data_only=True)
        try:
            if "Summary" not in workbook.sheetnames:
                result["reason"] = "FULL workbook has no Summary sheet"
                return result
            sheet = workbook["Summary"]
            rows = sheet.iter_rows(values_only=True)
            headers = next(rows, ())
            required = ("SampleID", "NeuronID", "Soma_Region", "Soma_Side")
            if any(headers.count(key) != 1 for key in required):
                result["reason"] = "Summary identity/side columns are missing or duplicated"
                return result
            columns = {key: headers.index(key) for key in required}
            matches = []
            for row_number, row in enumerate(rows, 2):
                if (str(row[columns["SampleID"]]).strip() == sample_id and
                        str(row[columns["NeuronID"]]).strip() == neuron_id):
                    matches.append((row_number, row))
                    if len(matches) > 1:
                        break
            if len(matches) != 1:
                result["reason"] = ("duplicate exact Summary identity" if matches else
                                    "exact Summary identity not found")
                return result
            row_number, row = matches[0]
            side = str(row[columns["Soma_Side"]] or "").strip().upper()
            region = str(row[columns["Soma_Region"]] or "").strip()
            prefix = region.split("_", 1)[0]
            if side not in {"L", "R"} or prefix not in {"CL", "CR", "SL", "SR"}:
                result["reason"] = "Summary side or region is missing or invalid"
                return result
            if (prefix.endswith("L") and side != "L") or (prefix.endswith("R") and side != "R"):
                result["reason"] = "Summary side conflicts with region prefix"
                return result
            result.update(status="verified", side="Left" if side == "L" else "Right",
                          reason="exact Summary identity and side/region agree",
                          source={"path": str(path), "sha256": digest, "bytes": len(payload),
                                  "sheet": "Summary", "row": row_number,
                                  "sample_id": sample_id, "neuron_id": neuron_id,
                                  "soma_side": side, "soma_region": region})
            return result
        finally:
            workbook.close()
    except (OSError, ValueError, ImportError, BadZipFile, IndexError, TypeError) as exc:
        result["reason"] = f"FULL workbook could not be verified: {exc}"
        return result
