"""Tests for the install flow, with no driver and no Windows required.

The seams that make this possible:

* ``installer.run`` is the single subprocess boundary -> fake it.
* ``registry.looks_installed`` is the single registry boundary -> fake it.
* ``probe.probe`` is the single driver-device boundary -> fake it.
* ``flow`` takes an ``emit`` callable -> capture output without capsys.
"""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from tkfacade.io.interception_setup import (
    driver,
    flow,
    installer,
    logon_task,
    paths,
    probe,
    registry,
    state,
)
from tkfacade.io.interception_setup.state import Stage, State


@pytest.fixture(autouse=True)
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect the state file into tmp_path for every test."""
    target = tmp_path / "driver_state.json"
    monkeypatch.setattr(paths, "state_file", lambda: target)
    yield target


@pytest.fixture
def fake_installer(tmp_path: Path) -> Path:
    exe = tmp_path / paths.INSTALLER_NAME
    exe.write_bytes(b"")
    return exe


class Recorder:
    """Collects emitted lines so assertions read cleanly."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, message: str) -> None:
        self.lines.append(message)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


# --------------------------------------------------------------------------
# vendored installer and self-invocation
# --------------------------------------------------------------------------


def test_vendored_installer_is_present() -> None:
    """The exe ships inside the package. A wrong constant breaks install
    silently -- after the UAC prompt, which is the worst place to find out."""
    assert paths.vendor_installer().is_file()


def test_self_argv_targets_this_package() -> None:
    """The logon task and the UAC relaunch both re-enter through this argv;
    a stale module path means verify never runs after a restart."""
    assert paths.MODULE_PATH in paths.self_argv("verify")


# --------------------------------------------------------------------------
# driver.install
# --------------------------------------------------------------------------


def test_install_missing_installer_fails(tmp_path: Path) -> None:
    result = driver.install(tmp_path / "nope.exe")
    assert result.stage is Stage.FAILED
    assert "missing" in result.detail


def test_install_respects_preexisting_driver(
    fake_installer: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "looks_installed", lambda: True)
    monkeypatch.setattr(registry, "describe", lambda: "keyboard, mouse")

    def unexpected(*_args: object, **_kwargs: object) -> installer.Result:
        pytest.fail("installer must not run when the driver already exists")

    monkeypatch.setattr(installer, "run", unexpected)

    result = driver.install(fake_installer)

    assert result.stage is Stage.PENDING_REBOOT
    assert result.we_installed_it is False


def test_install_fails_when_filters_never_appear(
    fake_installer: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "looks_installed", lambda: False)
    monkeypatch.setattr(
        installer,
        "run",
        lambda *_a, **_k: installer.Result(returncode=0, output="all good"),
    )

    result = driver.install(fake_installer)

    # Installer claimed success; no side effect observed. Side effect wins.
    assert result.stage is Stage.FAILED


def test_install_succeeds_despite_nonzero_exit(
    fake_installer: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[bool] = []

    def looks_installed() -> bool:
        # False on the pre-check, True after the installer ran.
        calls.append(True)
        return len(calls) > 1

    monkeypatch.setattr(registry, "looks_installed", looks_installed)
    monkeypatch.setattr(
        installer,
        "run",
        lambda *_a, **_k: installer.Result(returncode=1, output="could not write"),
    )

    result = driver.install(fake_installer)

    assert result.stage is Stage.PENDING_REBOOT
    assert result.we_installed_it is True
    assert "rc=1" in result.detail


# --------------------------------------------------------------------------
# driver.uninstall
# --------------------------------------------------------------------------


def test_uninstall_declines_when_not_ours(
    fake_installer: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected(*_args: object, **_kwargs: object) -> installer.Result:
        pytest.fail("must not remove a driver we did not install")

    monkeypatch.setattr(installer, "run", unexpected)

    previous = State(Stage.VERIFIED, we_installed_it=False)
    result = driver.uninstall(previous, fake_installer)

    assert result.stage is Stage.VERIFIED
    assert "left in place" in result.detail


def test_uninstall_force_overrides(fake_installer: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "looks_installed", lambda: False)
    monkeypatch.setattr(
        installer,
        "run",
        lambda *_a, **_k: installer.Result(returncode=0, output="removed"),
    )

    previous = State(Stage.VERIFIED, we_installed_it=False)
    result = driver.uninstall(previous, fake_installer, force=True)

    assert result.stage is Stage.ABSENT


def test_uninstall_keeps_ownership_when_installer_is_missing(tmp_path: Path) -> None:
    """Losing we_installed_it here would make every later uninstall decline."""
    previous = State(Stage.VERIFIED, we_installed_it=True)
    result = driver.uninstall(previous, tmp_path / "nope.exe")

    assert "missing" in result.detail
    assert result.we_installed_it is True


# --------------------------------------------------------------------------
# flow.run_verify
# --------------------------------------------------------------------------


def test_verify_reports_pending_when_filters_present_but_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(probe, "probe", lambda: probe.ProbeResult(False, "driver unreachable"))
    monkeypatch.setattr(registry, "looks_installed", lambda: True)
    monkeypatch.setattr(logon_task, "remove", lambda: None)

    out = Recorder()
    code = flow.run_verify(emit=out)

    assert code == flow.EXIT_NEEDS_REBOOT
    assert state.load().stage is Stage.PENDING_REBOOT
    assert "restart" in out.text.lower()


def test_verify_reports_failure_when_nothing_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(probe, "probe", lambda: probe.ProbeResult(False, "not importable"))
    monkeypatch.setattr(registry, "looks_installed", lambda: False)
    monkeypatch.setattr(logon_task, "remove", lambda: None)

    code = flow.run_verify(emit=Recorder())

    assert code == flow.EXIT_FAILED
    assert state.load().stage is Stage.FAILED


def test_verify_always_clears_the_trigger(monkeypatch: pytest.MonkeyPatch) -> None:
    """A broken install must not nag at every logon."""
    removed: list[bool] = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(probe, "probe", lambda: probe.ProbeResult(False, "boom"))
    monkeypatch.setattr(registry, "looks_installed", lambda: False)
    monkeypatch.setattr(logon_task, "remove", lambda: removed.append(True))

    flow.run_verify(emit=Recorder())

    assert removed == [True]


# --------------------------------------------------------------------------
# state persistence
# --------------------------------------------------------------------------


def test_corrupt_state_reads_as_absent(isolated_state: Path) -> None:
    isolated_state.parent.mkdir(parents=True, exist_ok=True)
    isolated_state.write_text("{not json", encoding="utf-8")
    assert state.load().stage is Stage.ABSENT


def test_state_roundtrip() -> None:
    original = State(Stage.PENDING_REBOOT, "detail here", we_installed_it=True)
    state.save(original)
    assert state.load() == original
