"""Elevation detection and self-relaunch via UAC.

Only ``install`` and ``uninstall`` need this. ``verify`` and ``status`` must
work unelevated, since the post-reboot task runs in the user's context.
"""

import ctypes
import subprocess
import sys
from pathlib import Path
from typing import Final

from . import paths

SW_SHOWNORMAL: Final = 1
_SHELL_EXECUTE_MIN_SUCCESS: Final = 32


def is_elevated() -> bool:
    """True when the current process has an elevated admin token."""
    if sys.platform != "win32":
        return False

    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except AttributeError, OSError:
        # shell32 unavailable. Callers gate on platform first, so treat this as
        # "definitely not elevated" rather than raising.
        return False


def relaunch_elevated(subcommand: str) -> bool:
    """Ask the user to re-run this process as admin via the UAC prompt.

    Returns True if the elevated process was launched, in which case the
    caller should exit immediately and let the new process take over. Returns
    False if the user declined the prompt.

    Note the elevated child gets a fresh console and a fresh state file
    handle; it re-runs the whole command rather than resuming mid-flight.
    """
    if sys.platform != "win32":
        return False

    target, *rest = paths.self_argv(subcommand, windowless=False)
    params = subprocess.list2cmdline(rest)

    result: int = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", target, params, str(Path.cwd()), SW_SHOWNORMAL
    )
    return result >= _SHELL_EXECUTE_MIN_SUCCESS
