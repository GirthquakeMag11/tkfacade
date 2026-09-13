"""Install / uninstall policy.

All the "should we?" decisions live here. This module never touches the
registry or subprocess directly beyond the seams below, so tests can inject
fakes for ``installer`` and ``registry``.
"""

from pathlib import Path

from . import installer, paths, registry
from .state import Stage, State


def install(installer_path: Path | None = None) -> State:
    """Install the driver, or recognise that it's already there.

    Assumes the caller has already confirmed elevation.
    """
    exe = installer_path or paths.vendor_installer()

    if not exe.is_file():
        return State(Stage.FAILED, f"vendored installer missing: {exe}")

    if registry.looks_installed():
        # Pre-existing install, possibly from another tool. Don't touch it, and
        # record that we don't own it so uninstall leaves it alone.
        return State(
            Stage.PENDING_REBOOT,
            f"driver already present; {registry.describe()}",
            we_installed_it=False,
        )

    result = installer.run(exe, installer.Action.INSTALL)

    # The exit code is a hint. The side effect is the evidence.
    if not registry.looks_installed():
        return State(
            Stage.FAILED,
            f"installer rc={result.returncode}: {result.output or '(no output)'}",
        )

    if not result.claims_success:
        # Filters landed but the tool complained. Proceed, but keep the
        # complaint in the record -- it'll matter in a bug report.
        return State(
            Stage.PENDING_REBOOT,
            f"filters registered despite rc={result.returncode}: {result.output}",
            we_installed_it=True,
        )

    return State(Stage.PENDING_REBOOT, result.output, we_installed_it=True)


def uninstall(
    previous: State,
    installer_path: Path | None = None,
    force: bool = False,
) -> State:
    """Remove the driver, unless we didn't install it.

    Leaving a shared driver behind is a much smaller harm than breaking
    another application that depends on it, so the default is to decline.
    """
    if not previous.we_installed_it and not force:
        return State(
            previous.stage,
            "driver was present before install; left in place (use --force to override)",
            we_installed_it=previous.we_installed_it,
        )

    exe = installer_path or paths.vendor_installer()
    if not exe.is_file():
        # Preserve ownership: dropping it here would make every later uninstall
        # decline, believing the driver predated us.
        return State(
            previous.stage,
            f"vendored installer missing: {exe}",
            we_installed_it=previous.we_installed_it,
        )

    result = installer.run(exe, installer.Action.UNINSTALL)

    if registry.looks_installed():
        return State(
            Stage.FAILED,
            f"filters still registered after uninstall: {result.output}",
            we_installed_it=previous.we_installed_it,
        )

    return State(Stage.ABSENT, "driver removed; restart to complete")
