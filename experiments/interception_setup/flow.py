"""Top-level commands. Owns all control flow and all user-facing output.

Each function returns a process exit code. Nothing here raises on expected
failures -- a failed driver install is a normal outcome to report, not an
exception to propagate.
"""

import sys
from collections.abc import Callable
from typing import Final

from . import driver, elevation, logon_task, probe, registry, state
from .state import Stage, State

EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
EXIT_NEEDS_REBOOT: Final = 2
EXIT_DECLINED_UAC: Final = 3
EXIT_WRONG_PLATFORM: Final = 4

Emit = Callable[[str], None]


def _emit(message: str) -> None:
    print(message)


def _require_windows(emit: Emit) -> bool:
    if sys.platform != "win32":
        emit("This setup only applies to Windows.")
        return False
    return True


def _require_elevation(subcommand: str, emit: Emit) -> int | None:
    """Return None if we may proceed, otherwise an exit code.

    On relaunch we exit rather than continue: the elevated child re-runs the
    whole command, and two processes racing the same install is worse than a
    duplicated UAC prompt.
    """
    if elevation.is_elevated():
        return None

    emit("Administrator rights are required to install the input driver.")
    if elevation.relaunch_elevated(subcommand):
        emit("Continuing in an elevated window.")
        return EXIT_OK

    emit("Elevation was declined; the driver was not installed.")
    return EXIT_DECLINED_UAC


def run_install(emit: Emit = _emit) -> int:
    if not _require_windows(emit):
        return EXIT_WRONG_PLATFORM

    if (code := _require_elevation("install", emit)) is not None:
        return code

    result = driver.install()
    state.save(result)

    if result.stage is Stage.FAILED:
        emit(f"Driver installation failed: {result.detail}")
        return EXIT_FAILED

    if not logon_task.register("verify"):
        # Non-fatal: the driver is installed, we just can't auto-verify.
        # Degrade to asking the user to confirm from inside the app.
        emit(
            "Driver installed, but the post-restart check could not be scheduled.\n"
            "Restart, then open the app and choose 'Check driver status'."
        )
        return EXIT_NEEDS_REBOOT

    emit(
        "Driver installed. Please restart your computer.\n"
        "Setup will verify itself automatically after you log back in."
    )
    return EXIT_NEEDS_REBOOT


def run_verify(emit: Emit = _emit) -> int:
    """Post-reboot check. Unelevated, read-only, self-cleaning."""
    if not _require_windows(emit):
        return EXIT_WRONG_PLATFORM

    previous = state.load()
    result = probe.probe()

    if result.reachable:
        state.save(State(Stage.VERIFIED, result.detail, previous.we_installed_it))
        emit("Input driver verified and ready.")
        outcome = EXIT_OK
    elif registry.looks_installed():
        # Filters are registered but we can't reach the driver: almost always
        # "hasn't rebooted yet". Keep PENDING_REBOOT rather than crying failure.
        state.save(
            State(
                Stage.PENDING_REBOOT,
                f"{result.detail} (filters present -- restart may still be pending)",
                previous.we_installed_it,
            )
        )
        emit("Driver not active yet. A restart is still required.")
        outcome = EXIT_NEEDS_REBOOT
    else:
        state.save(State(Stage.FAILED, result.detail, previous.we_installed_it))
        emit(f"Input driver is not working: {result.detail}")
        outcome = EXIT_FAILED

    # Always clear the trigger, including on failure -- otherwise a broken
    # install nags the user at every single logon.
    logon_task.remove()
    return outcome


def run_uninstall(force: bool = False, emit: Emit = _emit) -> int:
    if not _require_windows(emit):
        return EXIT_WRONG_PLATFORM

    if (code := _require_elevation("uninstall", emit)) is not None:
        return code

    previous = state.load()
    result = driver.uninstall(previous, force=force)
    state.save(result)
    logon_task.remove()

    if result.stage is Stage.FAILED:
        emit(f"Driver removal failed: {result.detail}")
        return EXIT_FAILED

    emit(result.detail)
    return EXIT_OK


def run_status(emit: Emit = _emit) -> int:
    """Read-only. Re-probes rather than trusting the recorded verdict, so the
    UI shows the truth after e.g. an anti-cheat tool removed the driver."""
    if not _require_windows(emit):
        return EXIT_WRONG_PLATFORM

    recorded = state.load()
    live = probe.probe()

    emit(f"recorded stage : {recorded.stage}")
    emit(f"recorded detail: {recorded.detail or '(none)'}")
    emit(f"installed by us: {recorded.we_installed_it}")
    emit(f"filters        : {registry.describe()}")
    emit(f"live probe     : {'reachable' if live.reachable else live.detail}")

    return EXIT_OK if live.reachable else EXIT_FAILED
