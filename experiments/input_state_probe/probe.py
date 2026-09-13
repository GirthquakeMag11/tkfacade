"""Witness what root-level input tracking can rely on, one check per claim.

Run with::

    xvfb-run -a uv run python -m experiments.input_state_probe.probe

The keyboard and mouse observer is ruled to hold input state on the
root — every key and button's
pressed-or-not, queryable from anywhere, with an async condition on
top. Each check here pins one Tk fact that design turns on: whether a
root-level ``bind_all`` really sees every press and release wherever
focus sits and without stealing the widgets' own bindings; what X11
autorepeat delivers while a key is held (the pattern the state filter
must hold steady through); what arrives — and does not — when the key
is released after focus left the application (the stuck-key trap and
the clearing policy); whether a posted menu's grab starves the
binding; that left and right modifier variants track as distinct keys;
and that synthetically generated events register identically, which is
the route the suite will drive the observer by.

Real device injection comes from ``xdotool`` (XTEST), so held keys
meet the X server's own autorepeat rather than a synthesized
imitation. Nothing here imports tkfacade.

The expectations coded below are the behaviour witnessed on Tk 8.6.14,
x11, under Xvfb with no window manager — see the README. A failure is
a finding, not necessarily a fault; the exit status is the number that
failed.
"""

import shutil
import subprocess
import sys
import time
import tkinter as tk

Report = tuple[bool, str]

Record = tuple[str, str, int]
"""One observed event: (kind, detail, X server timestamp)."""


def xdo(*args: str) -> None:
    """Run one xdotool command and give the server a moment to deliver."""
    subprocess.run(["xdotool", *args], check=True, capture_output=True)


class Bench:
    """A mapped root with an all-binding recorder and an entry to focus."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.geometry("300x200+10+10")
        self.records: list[Record] = []
        self.entry_hits: list[str] = []
        self.entry = tk.Entry(self.root)
        self.entry.pack()
        self.entry.bind("<KeyPress>", lambda e: self.entry_hits.append(e.keysym), add="+")
        for kind in ("KeyPress", "KeyRelease"):
            self.root.bind_all(
                f"<{kind}>", lambda e, k=kind: self.records.append((k, e.keysym, e.time)), add="+"
            )
        for kind in ("ButtonPress", "ButtonRelease"):
            self.root.bind_all(
                f"<{kind}>", lambda e, k=kind: self.records.append((k, str(e.num), e.time)), add="+"
            )
        self.root.update()
        xdo("windowfocus", "--sync", str(self.root.winfo_id()))
        self.root.update()
        self.entry.focus_force()
        self.root.update()

    def pump(self, seconds: float) -> None:
        """Process events for ``seconds`` of wall time."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)

    def close(self) -> None:
        self.root.destroy()


def check_all_binding_sees_the_four_kinds() -> Report:
    """A root ``bind_all`` sees real presses and releases, key and button."""
    bench = Bench()
    xdo("key", "--window", str(bench.root.winfo_id()), "a")
    xdo("mousemove", "--sync", "60", "60")
    xdo("click", "1")
    bench.pump(0.3)
    kinds = {kind for kind, _, _ in bench.records}
    entry_saw = list(bench.entry_hits)
    bench.close()
    ok = kinds >= {"KeyPress", "KeyRelease", "ButtonPress", "ButtonRelease"} and "a" in entry_saw
    return ok, f"kinds seen {sorted(kinds)}, entry's own binding saw {entry_saw}"


def check_autorepeat_pattern() -> Report:
    """A held key's autorepeat arrives as same-timestamp release/press pairs."""
    bench = Bench()
    xdo("keydown", "b")
    bench.pump(1.4)  # past the server's repeat delay, into the repeat train
    xdo("keyup", "b")
    bench.pump(0.3)
    events = [(k, t) for k, d, t in bench.records if d == "b"]
    bench.close()
    presses = sum(1 for k, _ in events if k == "KeyPress")
    releases = sum(1 for k, _ in events if k == "KeyRelease")
    # pair each repeat KeyRelease with the KeyPress that follows it and
    # compare timestamps: identical stamps are the repeat signature
    paired = 0
    for index in range(len(events) - 1):
        release_then_press = events[index][0] == "KeyRelease" and events[index + 1][0] == "KeyPress"
        if release_then_press and events[index][1] == events[index + 1][1]:
            paired += 1
    repeats = presses - 1
    ok = presses > 1 and releases == presses and paired == releases - 1
    return ok, (
        f"{presses} presses / {releases} releases while held, "
        f"{paired} release+press pairs share a timestamp ({repeats} repeats)"
    )


def check_release_lost_with_focus() -> Report:
    """A release after focus left the app never arrives; FocusOut does."""
    bench = Bench()
    focus_out: list[bool] = []
    bench.root.bind("<FocusOut>", lambda e: focus_out.append(True), add="+")
    other = tk.Tk()  # a second X client to take the input focus
    other.geometry("120x80+340+10")
    other.update()
    xdo("keydown", "c")
    bench.pump(0.2)
    xdo("windowfocus", "--sync", str(other.winfo_id()))
    bench.pump(0.2)
    xdo("keyup", "c")
    bench.pump(0.3)
    events = [(k, d) for k, d, _ in bench.records if d == "c"]
    saw_focus_out = bool(focus_out)
    other.destroy()
    bench.close()
    presses = [k for k, _ in events if k == "KeyPress"]
    releases = [k for k, _ in events if k == "KeyRelease"]
    ok = bool(presses) and not releases and saw_focus_out
    return ok, (
        f"saw {len(presses)} press(es), {len(releases)} release(s) after focus left, "
        f"FocusOut delivered: {saw_focus_out}"
    )


def check_menu_grab_and_the_binding() -> Report:
    """What the all-binding still sees while a posted menu holds its grab."""
    bench = Bench()
    menu = tk.Menu(bench.root, tearoff=False)
    menu.add_command(label="one")
    menu.post(bench.root.winfo_rootx() + 40, bench.root.winfo_rooty() + 40)
    bench.pump(0.2)
    before = len(bench.records)
    xdo("key", "d")
    bench.pump(0.3)
    during = [(k, d) for k, d, _ in bench.records[before:] if d == "d"]
    menu.unpost()
    bench.pump(0.1)
    bench.close()
    ok = len(during) >= 2  # press and release both reach the binding
    return ok, f"during the menu grab the binding saw {during or 'nothing'}"


def check_modifier_variants_are_distinct() -> Report:
    """Left and right shift arrive under their own keysyms.

    Injected by raw keycode (50/62, the Xvfb keymap's shifts): asked
    for the *keysym* ``Shift_R``, xdotool resolves it through the
    keymap and presses a helper ``Shift_L`` alongside — an instrument
    artifact witnessed here, not an X or Tk fact, and the trap the
    README records for anyone re-running this.
    """
    bench = Bench()
    xdo("keydown", "50")
    xdo("keyup", "50")
    xdo("keydown", "62")
    xdo("keyup", "62")
    bench.pump(0.3)
    names = [d for k, d, _ in bench.records if k == "KeyPress" and d.startswith("Shift")]
    bench.close()
    ok = names == ["Shift_L", "Shift_R"]
    return ok, f"shift presses arrived as {names}"


def check_synthetic_events_register_identically() -> Report:
    """``event_generate`` presses reach the all-binding with their keysym."""
    bench = Bench()
    bench.entry.event_generate("<KeyPress-e>")
    bench.entry.event_generate("<KeyRelease-e>")
    bench.entry.event_generate("<ButtonPress-2>")
    bench.entry.event_generate("<ButtonRelease-2>")
    bench.pump(0.2)
    seen = [(k, d) for k, d, _ in bench.records if d in ("e", "2")]
    bench.close()
    ok = seen == [
        ("KeyPress", "e"),
        ("KeyRelease", "e"),
        ("ButtonPress", "2"),
        ("ButtonRelease", "2"),
    ]
    return ok, f"generated events arrived as {seen}"


CHECKS = (
    check_all_binding_sees_the_four_kinds,
    check_autorepeat_pattern,
    check_release_lost_with_focus,
    check_menu_grab_and_the_binding,
    check_modifier_variants_are_distinct,
    check_synthetic_events_register_identically,
)


def main() -> int:
    """Run every check; the exit status is the number that failed."""
    if shutil.which("xdotool") is None:
        print("xdotool is required for device-level injection")
        return 1
    failures = 0
    for check in CHECKS:
        try:
            ok, detail = check()
        except Exception as error:
            ok, detail = False, f"raised {type(error).__name__}: {error}"
        verdict = "pass" if ok else "FAIL"
        print(f"{verdict}  {check.__name__}: {detail}")
        failures += 0 if ok else 1
    return failures


if __name__ == "__main__":
    sys.exit(main())
