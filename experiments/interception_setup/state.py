"""Persisted setup state.

The state file is the only channel between the elevated install phase and the
unelevated post-reboot verify phase, so it carries everything the later phase
needs to make decisions -- notably ``we_installed_it``.
"""

import json
import os
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path

from . import paths


class Stage(StrEnum):
    ABSENT = "absent"
    PENDING_REBOOT = "pending_reboot"
    VERIFIED = "verified"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class State:
    stage: Stage
    detail: str = ""
    we_installed_it: bool = False
    """False when the driver was already present before we ran.

    Uninstall must honour this: another tool may depend on the driver, and
    ripping it out from under them is worse than leaving it behind.
    """

    def with_detail(self, detail: str) -> State:
        return replace(self, detail=detail)

    @property
    def needs_reboot(self) -> bool:
        return self.stage is Stage.PENDING_REBOOT

    @property
    def ok(self) -> bool:
        return self.stage is Stage.VERIFIED


def save(state: State, path: Path | None = None) -> None:
    """Write state atomically, so a crash mid-write can't strand us with an
    unparseable file and no way to recover."""
    target = path or paths.state_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
    os.replace(tmp, target)


def load(path: Path | None = None) -> State:
    """Read state, treating any problem as ABSENT.

    A missing or corrupt file means "we don't know", and the safe
    interpretation of not knowing is that nothing is installed yet.
    """
    target = path or paths.state_file()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return State(Stage.ABSENT)

    if not isinstance(raw, dict):
        return State(Stage.ABSENT)

    try:
        stage = Stage(raw["stage"])
    except KeyError, ValueError:
        return State(Stage.ABSENT)

    return State(
        stage=stage,
        detail=str(raw.get("detail", "")),
        we_installed_it=bool(raw.get("we_installed_it", False)),
    )
