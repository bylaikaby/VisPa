"""Saved-path logging through GUI and legacy Windows text streams.

Version: 1.20.0 (local/unreleased)
Last updated: 2026-11-04
Change history: ../CHANGELOG.md
"""
import contextlib
import io
import queue
import unittest

from vispa.renderers.microscopy_panels import _print_saved_path
from vispa.reviewer import _LogStream


class SavedPathLoggingTests(unittest.TestCase):
    def test_gui_log_stream_preserves_unicode(self):
        sink = queue.Queue()
        with contextlib.redirect_stdout(_LogStream(sink)):
            _print_saved_path('Plot saved', '路径 space/soma.png')
        self.assertEqual(sink.get_nowait(), '> Plot saved: 路径 space/soma.png')

    def test_string_io_preserves_unicode(self):
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink):
            _print_saved_path('Tri-plot saved', '路径 space/trio.png')
        self.assertIn('路径 space/trio.png', sink.getvalue())

    def test_cp1252_console_escapes_only_unencodable_path(self):
        data = io.BytesIO()
        with io.TextIOWrapper(data, encoding='cp1252') as stream:
            with contextlib.redirect_stdout(stream):
                _print_saved_path('Plot saved', '路径 space/soma.png')
                stream.flush()
                self.assertIn('\\u8def\\u5f84 space/soma.png', data.getvalue().decode('cp1252'))


if __name__ == '__main__':
    unittest.main()
