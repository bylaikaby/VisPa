"""Verify the user-provided VisPa icon survives packaging and reaches Tk.

Version: 1.20.2 (local/unreleased)
Last updated: 2026-11-07
Change history: ../CHANGELOG.md
"""

from hashlib import sha256
from importlib import resources
from unittest import mock
import unittest

from PIL import Image

from vispa import reviewer


class GuiIconTests(unittest.TestCase):
    def test_packaged_artwork_and_multisize_icon(self):
        assets = resources.files('vispa').joinpath('assets')
        png = assets.joinpath('vispa.png')
        ico = assets.joinpath('vispa.ico')
        self.assertEqual(
            sha256(png.read_bytes()).hexdigest(),
            '8f8391806d9d9261deb62e9e68fc4c33b1e5f2db7b958a0e7095e548414014ac')
        with resources.as_file(ico) as icon_path, Image.open(icon_path) as icon:
            self.assertTrue({(16, 16), (32, 32), (48, 48), (256, 256)}
                            <= icon.ico.sizes())

    def test_gui_sets_packaged_icon_without_display(self):
        root = mock.Mock()
        with mock.patch.object(reviewer.tk, 'PhotoImage') as photo, \
                mock.patch.object(reviewer.sys, 'platform', 'win32'):
            reviewer._apply_window_icon(root)
        photo.assert_called_once()
        root.iconphoto.assert_called_once_with(True, photo.return_value)
        root.iconbitmap.assert_called_once()


if __name__ == '__main__':
    unittest.main()
