"""Legacy PA registration path strings.

Same-volume results stay ``os.path.relpath``. Windows raises ``ValueError``
when the finished output and the registry anchor are on different drives.
That call happens after the workbook or table exists, so the fallback keeps
the output path instead of dropping the receipt.

Version: 0.2.1 (local/unreleased)
Last updated: 2026-11-10
Change history:
- 2026-11-09: Same-drive paths stay relative. A Windows cross-drive pair keeps the finished output path.
Status: candidate
"""
from __future__ import annotations

import os


def legacy_registration_path(target, anchor_parent) -> str:
    """Return the registration path for one finished output."""
    try:
        return os.path.relpath(os.fspath(target), os.fspath(anchor_parent))
    except ValueError:
        return os.fspath(target)
