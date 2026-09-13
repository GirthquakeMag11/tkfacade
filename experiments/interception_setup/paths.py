"""Filesystem locations shared across install phases.

Kept dependency-free so every other module can import it, including in
environments where neither the driver nor the wrapper is present.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Final

APP_NAME: Final = "tkfacade"
MODULE_PATH: Final = "tkfacade.io.interception_setup"
INSTALLER_NAME: Final = "install-interception.exe"


def is_frozen() -> bool:
    """True when running from a PyInstaller-style bundle."""
    return getattr(sys, "frozen", False) is True


def installer_dir() -> Path:
    """Directory holding the vendored installer.

    The exe ships inside this package, so it travels with the source tree and
    lands in the wheel. PyInstaller rewrites ``__file__`` to point into its
    extraction directory, so this resolves in a frozen build too -- provided
    the spec collects the exe as package data.
    """
    return Path(__file__).resolve().parent


def vendor_installer() -> Path:
    """Path to the bundled ``install-interception.exe``."""
    return installer_dir() / INSTALLER_NAME


def local_app_data() -> Path:
    raw = os.environ.get("LOCALAPPDATA")
    return Path(raw) if raw else Path.home() / "AppData" / "Local"


def state_file() -> Path:
    """Per-user state file. Deliberately not machine-wide: the verify phase
    runs unelevated and must be able to write it."""
    return local_app_data() / APP_NAME / "driver_state.json"


def self_argv(subcommand: str, *, windowless: bool = True) -> list[str]:
    """Argv that re-invokes this application with ``subcommand``.

    ``windowless`` picks ``pythonw`` so no console flashes at logon. Elevation
    wants the opposite: the UAC-spawned window is where the user reads the
    outcome, so it passes ``windowless=False``.
    """
    if is_frozen():
        return [sys.executable, subcommand]

    interpreter = Path(sys.executable)
    if windowless:
        candidate = interpreter.with_name("pythonw.exe")
        if candidate.is_file():
            interpreter = candidate
    return [str(interpreter), "-m", MODULE_PATH, subcommand]


def self_command(subcommand: str, *, windowless: bool = True) -> str:
    """A single command line, for ``schtasks /tr`` and ``RunOnce``."""
    return subprocess.list2cmdline(self_argv(subcommand, windowless=windowless))
