"""Read-only progress for an existing FNT distance calculation.
Version: 0.1.1 (local/unreleased)
Last updated: 2026-11-18
Change history: ../../../CHANGELOG.md
- 2026-11-18: Validate both completed FNT producer receipt contracts and bound artifacts.
- 2026-11-18: Incremental pair counting, terminal/HTML progress and receipt-gated completion.
Status: candidate
"""
import argparse
import ctypes
import html
import hashlib
import json
import os
import time
from pathlib import Path

VERSION = "0.1.1"

def process_alive(pid):
    if os.name == "nt":
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        api.OpenProcess.restype = ctypes.c_void_p
        api.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        api.WaitForSingleObject.restype = ctypes.c_ulong
        api.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = api.OpenProcess(0x100000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 5:
                raise PermissionError("Cannot inspect producer process")
            return False
        try:
            return api.WaitForSingleObject(handle, 0) == 258
        finally:
            api.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False

class PairCounter:
    def __init__(self):
        self.offset = 0
        self.lines = 0
    def read(self, path):
        if not path.exists():
            return 0
        if path.stat().st_size < self.offset:
            raise ValueError("Distance output shrank; refusing to combine different runs")
        with path.open("rb") as stream:
            stream.seek(self.offset)
            while block := stream.read(1024 * 1024):
                self.lines += block.count(b"\n")
            self.offset = stream.tell()
        return max(0, self.lines - 1)

def _verified_receipt(receipt, expected, distance=None):
    try:
        saved = json.loads(receipt.read_text(encoding="utf-8"))
        metadata = saved["distance_metadata"]
        n = metadata["n_neurons"]
        if (type(n) is not int or n < 1 or n * (n + 1) // 2 != expected
                or metadata["n_input_pairs"] != expected):
            return False
        source = Path(saved["distance"])
        joined = Path(saved["joined_fnt"])
        if distance is not None and source.resolve() != Path(distance).resolve():
            return False
        def digest(path):
            h = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(block)
            return h.hexdigest()
        if (digest(source) != saved["distance_sha256"] or digest(joined) != saved["joined_sha256"]
                or metadata.get("distance_sha256") != saved["distance_sha256"]
                or metadata.get("joined_fnt_sha256") != saved["joined_sha256"]):
            return False
        if saved.get("status") == "complete":
            return saved.get("source_hashes_unchanged") is True
        if saved.get("schema") != "remap.fnt_pipeline.v1" or "status" in saved:
            return False
        cases = saved["cases"]
        planned = saved["plan"]["cases"]
        after = saved["source_sha256_after"]
        return (len(cases) == len(planned) == len(after) == n
                and all(a["uid"] == b["uid"] and a["swc_sha256"] == b["swc_sha256"]
                        and after.get(a["uid"]) == a["swc_sha256"] for a, b in zip(cases, planned)))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def snapshot(count, expected, elapsed, alive, receipt, distance=None):
    complete = _verified_receipt(receipt, expected, distance)
    state = "complete" if complete else "running" if alive else "awaiting_validation_or_failed"
    fraction = min(count / expected, 1)
    return {"status": state, "completed_pair_lines": count, "expected_pairs": expected,
            "percent": 100 * fraction, "elapsed_seconds": elapsed,
            "estimated_remaining_seconds": elapsed * (expected-count)/count if 0 < count < expected and alive else None,
            "estimate_note": "Approximate average-rate estimate; pairs have unequal cost and writes may be buffered",
            "completion_note": "Line count is progress only; producer receipt validates the matrix"}

def save_status(data, status_path, html_path=None):
    temporary = status_path.with_suffix(".json.pending")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temporary.replace(status_path)
    if html_path:
        remaining = data["estimated_remaining_seconds"]
        eta = "Not available" if remaining is None else f"{remaining/60:.0f} min (approximate)"
        page = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="60"><title>FNT calculation progress</title><style>body{{font:18px system-ui;max-width:760px;margin:5vh auto;padding:20px;background:#f6f8fb;color:#182b45}}progress{{width:100%;height:32px;accent-color:#2878b5}}small{{display:block;line-height:1.5;color:#526174}}h1{{font-size:1.6rem}}</style><h1>FNT calculation</h1><p>{html.escape(data['status'])} · {data['percent']:.1f}%</p><progress max="100" value="{data['percent']}"></progress><p>{data['completed_pair_lines']:,} / {data['expected_pairs']:,} pairs</p><p>Elapsed: {data['elapsed_seconds']/60:.1f} min<br>Remaining: {eta}</p><small>{html.escape(data['estimate_note'])}<br>{html.escape(data['completion_note'])}<br>Refreshes every60 seconds. Updated {html.escape(data['updated_at'])}.</small></html>"""
        html_path.write_text(page, encoding="utf-8")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--distance", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--html", type=Path)
    parser.add_argument("--neurons", type=int, required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--started-at", type=float, required=True, help="Producer start Unix timestamp")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.neurons < 1 or args.pid < 1 or not 5 <= args.interval <= 3600:
        parser.error("Require positive neurons/PID and interval5..3600 seconds")
    for destination in [args.status, args.html]:
        if destination and destination.resolve() in [args.distance.resolve(), args.receipt.resolve()]:
            parser.error("Status output cannot overwrite scientific files")
    counter = PairCounter()
    stopped_at = None
    while True:
        count = counter.read(args.distance)
        alive = process_alive(args.pid)
        data = snapshot(count, args.neurons*(args.neurons+1)//2, max(0,time.time()-args.started_at), alive, args.receipt, args.distance)
        data.update(pid=args.pid, updated_at=time.strftime("%Y-%m-%d %H:%M:%S %z"), version=VERSION)
        save_status(data, args.status, args.html)
        filled = int(min(data["percent"],100)*.3)
        print("["+"#"*filled+"-"*(30-filled)+f"] {data['percent']:.1f}% {count:,}/{data['expected_pairs']:,} pairs | {data['status']}", flush=True)
        if args.once or data["status"] == "complete":
            break
        if not alive:
            stopped_at = stopped_at or time.monotonic()
            if time.monotonic()-stopped_at > 300:
                break
        time.sleep(args.interval)

if __name__ == "__main__":
    main()
