"""Thin wrapper around the vendored ``install-interception.exe``.

Deliberately decision-free: it runs the process and reports what happened.
All policy lives in ``driver.py``, which keeps this module trivially fakeable
in tests.
"""

import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

CREATE_NO_WINDOW: Final = 0x08000000
TIMEOUT_SECONDS: Final = 120


class Action(StrEnum):
    INSTALL = "/install"
    UNINSTALL = "/uninstall"


@dataclass(frozen=True, slots=True)
class Result:
    returncode: int
    output: str
    timed_out: bool = False

    @property
    def claims_success(self) -> bool:
        """The installer's own opinion. Treat as a hint, not proof --
        always corroborate with an observed side effect."""
        return self.returncode == 0 and not self.timed_out


def run(installer: Path, action: Action) -> Result:
    """Invoke the installer.

    Two non-obvious requirements:

    * ``cwd`` must be the installer's own directory. It resolves the driver
      payload relative to itself, and has been reported to fail with a
      "could not write to \\system32\\drivers" message when run from
      elsewhere even in an elevated prompt.
    * stdout/stderr must be captured and logged regardless of exit status,
      because that message is the only diagnostic you get.
    """
    try:
        proc = subprocess.run(
            [str(installer), action.value],
            cwd=installer.parent,
            capture_output=True,
            text=True,
            check=False,
            timeout=TIMEOUT_SECONDS,
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return Result(returncode=-1, output="installer timed out", timed_out=True)
    except OSError as exc:
        return Result(returncode=-1, output=f"could not launch installer: {exc}")

    combined = "\n".join(part.strip() for part in (proc.stdout, proc.stderr) if part.strip())
    return Result(returncode=proc.returncode, output=combined)
