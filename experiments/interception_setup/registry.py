"""Pre-reboot presence heuristic via device class ``UpperFilters``.

This is NOT the authoritative check -- ``probe.py`` is. Its only jobs are:

* avoid a pointless reinstall when the driver is already present, and
* confirm the installer actually had an effect, since its exit code has been
  reported as unreliable.

The class GUIDs and service names below are confirmed against the vendored
``install-interception.exe`` itself, which carries the literal strings
``System\\CurrentControlSet\\Control\\Class\\{4D36E96B-...}`` (keyboard),
``{4D36E96F-...}`` (mouse), ``UpperFilters``, and the service paths
``System\\CurrentControlSet\\Services\\keyboard`` / ``...\\mouse``.
"""

import sys
from typing import Final

if sys.platform == "win32":
    import winreg
else:  # pragma: no cover - lets the test suite import on non-Windows CI
    winreg = None  # type: ignore[assignment]

# Standard Windows setup class GUIDs.
KEYBOARD_CLASS: Final = "{4D36E96B-E325-11CE-BFC1-08002BE10318}"
MOUSE_CLASS: Final = "{4D36E96F-E325-11CE-BFC1-08002BE10318}"

CLASS_KEY_TEMPLATE: Final = r"SYSTEM\CurrentControlSet\Control\Class\{guid}"

# Interception registers generically-named filter services; it drops
# keyboard.sys and mouse.sys into \system32\drivers.
EXPECTED_FILTERS: Final = frozenset({"keyboard", "mouse"})


def upper_filters(class_guid: str) -> tuple[str, ...]:
    """Read the ``UpperFilters`` multi-string for a device setup class.

    Returns an empty tuple when the key or value is absent, which is the
    normal state on a machine with no filter drivers installed.
    """
    if sys.platform != "win32":
        return ()

    key_path = CLASS_KEY_TEMPLATE.format(guid=class_guid)
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            value, _kind = winreg.QueryValueEx(key, "UpperFilters")
    except OSError:
        return ()

    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return (str(value),)


def looks_installed() -> bool:
    """Best-effort: does a filter matching our expected names sit on either
    the keyboard or mouse class?"""
    if sys.platform != "win32":
        return False

    found = {name.lower() for guid in (KEYBOARD_CLASS, MOUSE_CLASS) for name in upper_filters(guid)}
    return any(expected in found for expected in EXPECTED_FILTERS)


def describe() -> str:
    """Human-readable filter listing, for logs and bug reports."""
    keyboard = ", ".join(upper_filters(KEYBOARD_CLASS)) or "(none)"
    mouse = ", ".join(upper_filters(MOUSE_CLASS)) or "(none)"
    return f"keyboard UpperFilters: {keyboard}; mouse UpperFilters: {mouse}"
