"""Credential-free parsing of VisPa release and update records.

Version: 1.20.1 (local/unreleased)
Last updated: 2026-11-04
Change history: ../../CHANGELOG.md
Status: candidate

The parser accepts the repository CHANGELOG, a local JSON/Markdown file, or a
plain HTTP(S) URL. It never invokes Git and sends no authorization header, so a
public or intranet-hosted static feed is sufficient. Access control remains the
hosting service's responsibility.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ._version import __version__

SCHEMA = "vispa.updates.v1"
MAX_SOURCE_BYTES = 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 5.0

_RELEASE_HEADING = re.compile(
    r"^##\s+\[?(?P<version>[^\s\]]+)\]?\s+[—–-]\s+"
    r"(?P<date>\d{4}-\d{2}-\d{2})"
    r"(?:\s+\((?P<status>[^)]+)\))?\s*$"
)


def _validate_date(value, label):
    text = str(value or "").strip()
    try:
        year, month, day = (int(part) for part in text.split("-"))
        from datetime import date

        date(year, month, day)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an ISO date (YYYY-MM-DD)") from exc
    return text


def _clean_changes(values, label):
    if not isinstance(values, list):
        raise ValueError(f"{label}.changes must be a list of strings")
    changes = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label}.changes entries must be nonempty strings")
        changes.append(value.strip())
    return changes


def _normalize_releases(releases, *, source):
    normalized = []
    seen = set()
    for index, release in enumerate(releases):
        label = f"{source}: release {index + 1}"
        if not isinstance(release, dict):
            raise ValueError(f"{label} must be an object")
        version = str(release.get("version") or "").strip().lstrip("v")
        if not version or any(character.isspace() for character in version):
            raise ValueError(f"{label}.version must be a nonempty version string")
        if version in seen:
            raise ValueError(f"{source}: duplicate release version {version!r}")
        seen.add(version)
        entry = {
            "version": version,
            "date": _validate_date(release.get("date"), f"{label}.date"),
            "status": (str(release["status"]).strip()
                       if release.get("status") else None),
            "changes": _clean_changes(
                release.get("changes", []), label),
        }
        observed_dates = release.get("dates")
        if observed_dates:
            if not isinstance(observed_dates, list):
                raise ValueError(f"{label}.dates must be a list")
            normalized_dates = []
            for date_index, value in enumerate(observed_dates):
                date_text = _validate_date(
                    value, f"{label}.dates[{date_index}]")
                if date_text not in normalized_dates:
                    normalized_dates.append(date_text)
            if len(normalized_dates) > 1:
                entry["dates"] = normalized_dates
        for optional in ("commit", "reference"):
            value = release.get(optional)
            if value:
                entry[optional] = str(value).strip()
        normalized.append(entry)
    if not normalized:
        raise ValueError(f"{source}: no update releases found")
    return normalized


def parse_update_changelog(text, *, source="<memory>"):
    """Parse Markdown release headings and their bullet items into a feed.

    Input is text containing headings such as
    ``## 1.20.0 — 2026-11-04 (local/unreleased)``.
    The output is deterministic and contains normalized release records. Reuse
    this parser when the canonical CHANGELOG remains the update source and no
    separate publishing service is needed.
    """
    if not isinstance(text, str):
        raise TypeError("update changelog content must be text")
    releases = []
    current = None
    current_change = None

    def finish_change():
        nonlocal current_change
        if current is not None and current_change:
            current["changes"].append(" ".join(" ".join(current_change).split()))
        current_change = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        match = _RELEASE_HEADING.match(line)
        if match:
            finish_change()
            current = {
                "version": match.group("version").strip().lstrip("v"),
                "date": _validate_date(match.group("date"), source),
                "status": (match.group("status").strip()
                           if match.group("status") else None),
                "changes": [],
            }
            releases.append(current)
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            finish_change()
            current_change = [stripped[2:].strip()]
        elif current_change and raw_line.startswith((" ", "\t")) and stripped:
            current_change.append(stripped)
        elif not stripped:
            finish_change()
    finish_change()
    merged = []
    by_version = {}
    for release in releases:
        existing = by_version.get(release["version"])
        if existing is None:
            merged.append(release)
            by_version[release["version"]] = release
            continue
        if existing["date"] != release["date"]:
            dates = existing.setdefault("dates", [existing["date"]])
            if release["date"] not in dates:
                dates.append(release["date"])
        for change in release["changes"]:
            if change not in existing["changes"]:
                existing["changes"].append(change)
        if not existing.get("status") and release.get("status"):
            existing["status"] = release["status"]
    releases = merged
    releases = _normalize_releases(releases, source=source)
    return {
        "schema": SCHEMA,
        "source": str(source),
        "format": "changelog",
        "installed_version": __version__,
        "latest_version": releases[0]["version"],
        "matches_installed": releases[0]["version"] == __version__.lstrip("v"),
        "releases": releases,
    }


def parse_update_feed(payload, *, source="<memory>"):
    """Parse a static ``vispa.updates.v1`` JSON document."""
    try:
        document = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{source}: invalid update-feed JSON") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{source}: update feed must be a JSON object")
    schema = document.get("schema")
    if schema not in (None, SCHEMA):
        raise ValueError(f"{source}: unsupported update-feed schema {schema!r}")
    raw_releases = document.get("releases")
    if not isinstance(raw_releases, list):
        raise ValueError(f"{source}: releases must be a JSON list")
    releases = _normalize_releases(raw_releases, source=source)
    return {
        "schema": SCHEMA,
        "source": str(source),
        "format": "json",
        "installed_version": __version__,
        "latest_version": releases[0]["version"],
        "matches_installed": releases[0]["version"] == __version__.lstrip("v"),
        "releases": releases,
    }


def parse_updates(payload, *, source="<memory>", format=None):
    """Parse either Markdown or JSON update content.

    ``format`` may be ``"json"`` or ``"changelog"``. When omitted, JSON is
    detected by its first non-whitespace character and Markdown is the fallback.
    """
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8-sig")
    if not isinstance(payload, str):
        raise TypeError("update content must be text or UTF-8 bytes")
    selected = format
    if selected is None:
        selected = "json" if payload.lstrip().startswith("{") else "changelog"
    if selected == "json":
        return parse_update_feed(payload, source=source)
    if selected == "changelog":
        return parse_update_changelog(payload, source=source)
    raise ValueError("format must be 'json' or 'changelog'")


def _default_source():
    configured = os.environ.get("VISPA_UPDATES_SOURCE")
    if configured:
        return configured
    repository = Path(__file__).resolve().parents[2]
    candidate = repository / "CHANGELOG.md"
    if candidate.is_file():
        return candidate
    if (repository / ".git").exists():
        return "git"
    return None


def _git_environment():
    environment = os.environ.copy()
    environment.update({
        "GCM_INTERACTIVE": "Never",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
    })
    return environment


def load_git_updates(repository=None, *, revision="HEAD", limit=50,
                     timeout=DEFAULT_TIMEOUT_SECONDS):
    """Parse recent commits from an existing local clone without network access.

    Only local Git objects reachable from ``revision`` are inspected. The helper
    runs with terminal prompts and credential-manager interaction disabled, so a
    missing remote credential cannot stop the operation. It never calls fetch,
    pull, ls-remote, GitHub APIs, or another network-facing Git command.
    """
    if not 1 <= int(limit) <= 50:
        raise ValueError("git update limit must be between 1 and 50")
    candidate = Path(repository).expanduser() if repository else (
        Path(__file__).resolve().parents[2])
    environment = _git_environment()
    common = [
        "git", "-C", str(candidate),
        "-c", "credential.helper=",
        "-c", "core.pager=cat",
    ]
    root_result = subprocess.run(
        [*common, "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL, env=environment, timeout=float(timeout),
        check=False,
    )
    if root_result.returncode != 0:
        detail = root_result.stderr.strip() or root_result.stdout.strip()
        raise ValueError(
            f"{candidate}: not a readable local Git checkout"
            f"{(': ' + detail) if detail else ''}")
    repository_root = Path(root_result.stdout.strip()).resolve()
    format_string = "%H%x00%h%x00%cs%x00%s%x00%b%x00%D%x1e"
    result = subprocess.run(
        [
            *common, "--no-pager", "log", revision,
            f"-n{int(limit)}", "--date=short", "--no-show-signature",
            f"--format={format_string}",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL, env=environment, timeout=float(timeout),
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(
            f"{repository_root}: cannot read local Git history"
            f"{(': ' + detail) if detail else ''}")
    releases = []
    for record in result.stdout.split("\x1e"):
        record = record.strip("\r\n")
        if not record:
            continue
        fields = record.split("\x00")
        if len(fields) != 6:
            raise ValueError(
                f"{repository_root}: malformed local Git update record")
        full, short, date, subject, body, decorations = fields
        tags = re.findall(r"tag: ([^,]+)", decorations)
        changes = [subject.strip()]
        for line in body.splitlines():
            item = line.strip().lstrip("-* ").strip()
            if item:
                changes.append(item)
        releases.append({
            "version": (tags[0].strip() if tags else short.strip()),
            "date": date.strip(),
            "status": "local git commit",
            "changes": [item for item in changes if item],
            "commit": full.strip(),
            "reference": revision,
        })
    releases = _normalize_releases(releases, source=str(repository_root))
    return {
        "schema": SCHEMA,
        "source": str(repository_root),
        "format": "git",
        "installed_version": __version__,
        "latest_version": releases[0]["version"],
        "matches_installed": releases[0]["version"] == __version__.lstrip("v"),
        "releases": releases,
    }


def load_updates(source=None, *, timeout=DEFAULT_TIMEOUT_SECONDS,
                 max_bytes=MAX_SOURCE_BYTES, repository=None, git_limit=50):
    """Load updates from local files, plain HTTP(S), or existing local Git data.

    The default is ``VISPA_UPDATES_SOURCE`` when set, otherwise the repository
    ``CHANGELOG.md`` in an editable checkout. Static JSON feeds are useful when
    the CLI is installed outside the source checkout. Source ``"git"`` reads
    local commit objects only; credential prompts and remote Git operations are
    disabled. Network requests use plain HTTP(S) without an authorization header.
    """
    selected = source or _default_source()
    if not selected:
        raise ValueError(
            "no update source found; pass --source or set VISPA_UPDATES_SOURCE")
    source_text = str(selected)
    if source_text.lower() in {"git", "local-git"}:
        return load_git_updates(
            repository, limit=git_limit, timeout=timeout)
    if source_text.lower().startswith("git:"):
        return load_git_updates(
            source_text.partition(":")[2] or repository,
            limit=git_limit, timeout=timeout)
    is_http = source_text.lower().startswith(("http://", "https://"))
    if "://" in source_text and not is_http:
        raise ValueError("update source URLs must use http:// or https://")

    if is_http:
        parsed = urlparse(source_text)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("update source URL must include an http(s) host")
        request = Request(
            source_text,
            headers={"User-Agent": f"VisPa/{__version__}"},
        )
        with urlopen(request, timeout=float(timeout)) as response:
            declared_length = response.headers.get("Content-Length")
            if declared_length:
                try:
                    length = int(declared_length)
                except ValueError as exc:
                    raise ValueError(
                        "update source returned an invalid Content-Length") from exc
                if length > max_bytes:
                    raise ValueError(
                        f"update source exceeds {max_bytes} bytes")
            content = response.read(int(max_bytes) + 1)
            charset = response.headers.get_content_charset() or "utf-8-sig"
    else:
        path = Path(source_text).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"update source does not exist: {path}")
        if path.stat().st_size > max_bytes:
            raise ValueError(f"update source exceeds {max_bytes} bytes")
        content = path.read_bytes()
        charset = "utf-8-sig"

    if len(content) > max_bytes:
        raise ValueError(f"update source exceeds {max_bytes} bytes")
    try:
        text = content.decode(charset)
    except (LookupError, UnicodeDecodeError) as exc:
        raise ValueError(
            f"{source_text}: update source is not valid {charset} text") from exc
    return parse_updates(text, source=source_text)
