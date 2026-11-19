"""Temporary directories for tests, kept under this package's work folder."""
import tempfile
from pathlib import Path

PACKAGE_TEST_TMP = Path(__file__).resolve().parents[1] / "work" / "test_tmp"


def local_temp():
    """Return a TemporaryDirectory whose files stay inside the package."""
    PACKAGE_TEST_TMP.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=PACKAGE_TEST_TMP)
