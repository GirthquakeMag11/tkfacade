"""One-shot post-reboot trigger for the verify phase.

Two strategies, both per-user and both removable:

* A scheduled task with a logon trigger and a delay. Preferred: it survives
  Safe Mode and doesn't race the shell coming up.
* ``RunOnce``. Simpler and self-deleting, but it fires very early in logon and
  is skipped in Safe Mode.

Register one, not both. ``remove()`` clears both so cleanup is idempotent
regardless of which path was used.
"""

import subprocess
import sys
from typing import Final

if sys.platform == "win32":
    import winreg
else:  # pragma: no cover - lets the test suite import on non-Windows CI
    winreg = None  # type: ignore[assignment]

from . import paths

TASK_NAME: Final = "TkfacadeInterceptionVerify"
RUNONCE_KEY: Final = r"Software\Microsoft\Windows\CurrentVersion\RunOnce"
LOGON_DELAY: Final = "0000:30"


def register_scheduled_task(subcommand: str = "verify") -> bool:
    """Create a delayed logon task that runs once and deletes itself.

    ``/tr`` quoting is the fragile part here. Test with an install path that
    contains spaces before shipping; if schtasks mangles it, use
    ``register_runonce()`` instead.
    """
    command = paths.self_command(subcommand)
    try:
        subprocess.run(
            [
                "schtasks",
                "/create",
                "/f",
                "/tn",
                TASK_NAME,
                "/tr",
                command,
                "/sc",
                "ONLOGON",
                "/delay",
                LOGON_DELAY,
            ],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError, OSError:
        return False
    return True


def register_runonce(subcommand: str = "verify") -> bool:
    """Fallback: HKCU RunOnce. Windows deletes the value before running it."""
    command = paths.self_command(subcommand)
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUNONCE_KEY) as key:
            winreg.SetValueEx(key, TASK_NAME, 0, winreg.REG_SZ, command)
    except OSError:
        return False
    return True


def register(subcommand: str = "verify") -> bool:
    """Try the scheduled task, fall back to RunOnce."""
    return register_scheduled_task(subcommand) or register_runonce(subcommand)


def remove() -> None:
    """Clear both trigger types. Safe to call when neither exists.

    Called unconditionally at the end of verify -- including on failure, so a
    broken install can't produce a trigger that fires at every logon forever.
    """
    subprocess.run(
        ["schtasks", "/delete", "/f", "/tn", TASK_NAME],
        capture_output=True,
        check=False,
    )
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUNONCE_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, TASK_NAME)
    except OSError:
        pass
