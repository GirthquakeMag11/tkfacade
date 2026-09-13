"""The ``mpv`` import, and the one thing that must happen before it.

``python-mpv`` loads libmpv while *it* is imported, through
``ctypes.util.find_library``, which on Windows searches ``PATH``, so
the vendored copy's directory is prepended there first. libmpv is
required by this module alone: the package resolves the video classes
lazily and imports this only when a display is constructed, so a
machine without libmpv pays at that moment rather than at ``import
tkfacade``. A failed import here still means libmpv is missing, and is
left to raise.
"""

import os
from pathlib import Path
from typing import Final

LIBMPV_DIR: Final[Path] = Path(__file__).parent / "libmpv"
"""Directory of the libmpv copy shipped alongside this package."""

os.environ["PATH"] = f"{LIBMPV_DIR!s}{os.pathsep}{os.environ.get('PATH', '')}"

from mpv import MPV as MPV  # type: ignore[import-untyped]
