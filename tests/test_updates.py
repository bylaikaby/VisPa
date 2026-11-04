"""Tests for credential-free update parsing and the public CLI surface.

Version: 1.13.0.dev16 (local/unreleased)
Last updated: 2026-11-04
Change history: ../CHANGELOG.md
Status: candidate
"""
from __future__ import annotations

from email.message import Message
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from vispa import cli
from vispa.updates import load_updates, parse_updates


class UpdateParserTests(unittest.TestCase):
    def test_parse_changelog_preserves_release_order_and_continuations(self):
        report = parse_updates(
            "# Changes\n\n"
            "## 2.0.0 — 2026-12-02 (candidate)\n"
            "- Larger version labels.\n"
            "  Continued explanation.\n"
            "- Scrollable resource list.\n\n"
            "## 1.9.1 — 2026-11-30\n"
            "- Previous release.\n",
            source="CHANGELOG.md",
        )

        self.assertEqual(report["format"], "changelog")
        self.assertEqual(report["latest_version"], "2.0.0")
        self.assertEqual(
            report["releases"][0]["changes"],
            ["Larger version labels. Continued explanation.",
             "Scrollable resource list."],
        )
        self.assertEqual(report["releases"][1]["changes"],
                         ["Previous release."])

    def test_parse_changelog_merges_repeated_version_sections(self):
        report = parse_updates(
            "## 1.4.0 — 2026-12-01\n"
            "- First section.\n"
            "## 1.4.0 — 2026-12-01\n"
            "- Second section.\n",
            source="CHANGELOG.md",
        )

        self.assertEqual(len(report["releases"]), 1)
        self.assertEqual(
            report["releases"][0]["changes"],
            ["First section.", "Second section."],
        )

    def test_parse_json_feed_validates_schema_date_and_changes(self):
        report = parse_updates(json.dumps({
            "schema": "vispa.updates.v1",
            "releases": [{
                "version": "v3.1.0",
                "date": "2026-12-03",
                "status": "released",
                "changes": ["Static feed update."],
            }],
        }), source="https://example.test/updates.json")

        self.assertEqual(report["format"], "json")
        self.assertEqual(report["releases"][0]["version"], "3.1.0")
        self.assertEqual(report["source"], "https://example.test/updates.json")

    def test_parse_rejects_duplicate_versions_and_invalid_dates(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_updates(
                '{"releases": ['
                '{"version":"1.0","date":"2026-01-01"},'
                '{"version":"1.0","date":"2026-01-02"}]}',
                source="duplicates.json",
            )
        with self.assertRaisesRegex(ValueError, "ISO date"):
            parse_updates(
                '{"releases":[{"version":"1.0","date":"not-a-date"}]}',
                source="bad-date.json",
            )

    def test_load_http_source_uses_plain_request_without_authorization(self):
        message = Message()
        message["Content-Length"] = "87"

        class Response:
            headers = message

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size):
                self.read_size = size
                return (
                    b"## 9.0.0 - 2026-12-04\n"
                    b"- Public static feed.\n"
                )

        response = Response()
        with mock.patch("vispa.updates.urlopen", return_value=response) as opened:
            report = load_updates("https://example.test/CHANGELOG.md")

        request = opened.call_args.args[0]
        self.assertIsNone(request.get_header("Authorization"))
        self.assertIn("VisPa/", request.get_header("User-agent"))
        self.assertEqual(opened.call_args.kwargs["timeout"], 5.0)
        self.assertEqual(response.read_size, 1024 * 1024 + 1)
        self.assertEqual(report["latest_version"], "9.0.0")

    def test_load_local_source_and_cli_json(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "updates.json"
            source.write_text(json.dumps({
                "schema": "vispa.updates.v1",
                "releases": [
                    {"version": "2.0", "date": "2026-12-02",
                     "changes": ["Second."]},
                    {"version": "1.0", "date": "2026-12-01",
                     "changes": ["First."]},
                ],
            }), encoding="utf-8")
            local = load_updates(source)
            output = io.StringIO()
            with mock.patch("sys.stdout", output):
                result = cli.main([
                    "updates", "--source", str(source),
                    "--limit", "1", "--json",
                ])

        self.assertEqual(local["latest_version"], "2.0")
        self.assertEqual(result, 0)
        self.assertEqual(len(json.loads(output.getvalue())["releases"]), 1)

    def test_unsupported_remote_scheme_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "http"):
            load_updates("ftp://example.test/updates.json")

    def test_git_source_parses_existing_local_history_without_prompts(self):
        repository = Path(__file__).resolve().parents[1]
        report = load_updates(
            "git", repository=repository, git_limit=2)

        self.assertEqual(report["format"], "git")
        self.assertGreaterEqual(len(report["releases"]), 1)
        self.assertTrue(report["releases"][0]["commit"])
        self.assertEqual(report["releases"][0]["reference"], "HEAD")


if __name__ == "__main__":
    unittest.main()
