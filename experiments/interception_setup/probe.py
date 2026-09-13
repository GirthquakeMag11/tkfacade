"""Read-only driver reachability check. The authoritative verdict.

Asks Windows whether the driver's device objects exist, by trying to open one
and closing it again. That is the whole test: ``\\\\.\\InterceptionNN`` exists
only while the filter driver is loaded. A busy or access-denied device still
counts as present -- see ``_device_exists`` for why that distinction matters.

CRITICAL: this runs at logon, when focus may be on a password field, a
Windows Hello prompt, or a lock screen. It must never emit input. An
open/close pair cannot -- it issues no ``DeviceIoControl`` at all, so no code
path here can reach the driver's write entry point.

Deliberately does not import the ``interception`` wrapper. That package does
``import win32api`` at module scope (``interception/_utils.py``), which would
drag pywin32 into a project that also has to install on Linux -- and it is not
even a declared dependency of ``interception-python``, so the import fails
outright. Nothing is lost: the wrapper's own notion of "driver present" is
``len(self._devices) > 0``, and ``_devices`` is filled by exactly the
``CreateFile`` call made below (see ``Interception.get_handles``).

Device names are confirmed from two directions: the vendored installer's
embedded strings contain ``\\Device\\Interception00`` and
``\\Device\\Interception10`` with ``\\DosDevices\\`` aliases, and the wrapper
opens ``\\\\.\\interceptionNN`` for the same range.
"""

import ctypes
import sys
from dataclasses import dataclass
from typing import Final

DEVICE_TEMPLATE: Final = r"\\.\Interception{num:02d}"

# Keyboards occupy slots 0-9, mice 10-19.
DEVICE_SLOTS: Final = range(20)

GENERIC_READ: Final = 0x80000000
OPEN_EXISTING: Final = 3
INVALID_HANDLE_VALUE: Final = ctypes.c_void_p(-1).value

# Don't demand exclusivity: we only want to know the device object is there.
FILE_SHARE_READ_WRITE: Final = 0x00000001 | 0x00000002

# Only these two mean "no such device object". Anything else -- busy, denied --
# is still proof the filter driver loaded, which is the only question asked here.
ERROR_FILE_NOT_FOUND: Final = 2
ERROR_PATH_NOT_FOUND: Final = 3
DEVICE_ABSENT_ERRORS: Final = frozenset({ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND})

if sys.platform == "win32":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # ctypes defaults restype to c_int, which truncates a 64-bit HANDLE and
    # makes the INVALID_HANDLE_VALUE comparison unreliable. Declare both ends.
    _kernel32.CreateFileW.restype = ctypes.c_void_p
    _kernel32.CreateFileW.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    )
    _kernel32.CloseHandle.restype = ctypes.c_int
    _kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
else:  # pragma: no cover - lets the test suite import on non-Windows CI
    _kernel32 = None


@dataclass(frozen=True, slots=True)
class ProbeResult:
    reachable: bool
    detail: str


def _device_exists(name: str) -> bool:
    """True when the device object ``name`` is present.

    Deliberately not "could we open it". Interception's own clients open these
    devices exclusively, so a running client would make an open-or-fail test
    report a perfectly healthy driver as missing. The device object only exists
    while the filter driver is loaded, so its presence is the real signal.
    """
    if sys.platform != "win32":
        return False

    ctypes.set_last_error(0)
    handle = _kernel32.CreateFileW(
        name, GENERIC_READ, FILE_SHARE_READ_WRITE, None, OPEN_EXISTING, 0, None
    )
    if handle is not None and handle != INVALID_HANDLE_VALUE:
        _kernel32.CloseHandle(handle)
        return True

    return ctypes.get_last_error() not in DEVICE_ABSENT_ERRORS


def probe() -> ProbeResult:
    """Report whether the filter driver is attached and reachable.

    Scans every device slot rather than stopping at the first, because which
    slots exist depends on what hardware is attached -- a machine with no
    keyboard filter instance can still have a working mouse one.
    """
    if sys.platform != "win32":
        return ProbeResult(False, "driver probe is only meaningful on Windows")

    for num in DEVICE_SLOTS:
        name = DEVICE_TEMPLATE.format(num=num)
        try:
            present = _device_exists(name)
        except OSError as exc:
            return ProbeResult(False, f"could not query {name}: {exc}")
        if present:
            return ProbeResult(True, f"driver reachable ({name})")

    return ProbeResult(
        False,
        f"no interception device responded ({DEVICE_TEMPLATE.format(num=0)}"
        f"..{DEVICE_TEMPLATE.format(num=DEVICE_SLOTS[-1])})",
    )
