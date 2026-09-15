"""Does the CI runner session give Tk a reliable clipboard?

One-shot diagnostic (workflow_dispatch only; see
.github/workflows/clipboard-probe.yml). Written after four Windows CI
crashes clustered around clipboard / read-only-widget operations
(tkfacade issue #5) to separate three suspects: the OS session's
clipboard, Tk's clipboard path, and the read-only + synthetic-event
confound.

Run as parent (no args): executes every phase, each in its own subprocess
and repeated, so an access violation in one phase cannot mask another,
and prints a verdict table. Run as child (one phase name as argv[1]):
executes that phase, flushing progress so the last printed iteration
localizes a crash.

Phases:
  info             interpreter, Tcl/Tk, session and window-station facts
  win32            pure ctypes user32/kernel32 clipboard round-trips —
                   the session's clipboard with no Tk involved
                   (Windows only; skipped elsewhere)
  tk-basic         Tk clipboard clear/append/get round-trips, one root
  tk-empty-get     Tk clipboard_get with the clipboard empty — the error
                   path, which must raise a Tcl error, not fault
  tk-stress        200 round-trips, a fresh root every 20 — reliability
                   under repetition and root churn
  readonly-events  100 iterations of the crashing tests' exact confound
                   in pure Tk (no tkfacade): seed the clipboard, then
                   synthetic select-all/copy/paste/keystroke events
                   against a read-only Entry and a disabled Text,
                   reading the clipboard back each time
"""

from __future__ import annotations

import subprocess
import sys

PHASES = ("info", "win32", "tk-basic", "tk-empty-get", "tk-stress", "readonly-events")
REPEATS = 3
CHILD_TIMEOUT = 600

ACCESS_VIOLATION = 3221225477  # 0xC0000005, how Windows reports the fault


# ---------------------------------------------------------------- info

def phase_info() -> None:
    import platform

    print(f"python {sys.version} at {sys.executable}", flush=True)
    print(f"platform {platform.platform()} / {platform.machine()}", flush=True)
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        pid = kernel32.GetCurrentProcessId()
        session = ctypes.c_ulong()
        kernel32.ProcessIdToSessionId(pid, ctypes.byref(session))
        print(f"session id: {session.value}", flush=True)
        try:
            station = user32.GetProcessWindowStation()
            length = ctypes.c_ulong()
            user32.GetUserObjectInformationW(
                station, 2, None, 0, ctypes.byref(length)
            )
            buf = ctypes.create_unicode_buffer(length.value)
            user32.GetUserObjectInformationW(
                station, 2, buf, length, ctypes.byref(length)
            )
            print(f"window station: {buf.value!r}", flush=True)
            desktop = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
            user32.GetUserObjectInformationW(
                desktop, 2, None, 0, ctypes.byref(length)
            )
            buf2 = ctypes.create_unicode_buffer(length.value)
            user32.GetUserObjectInformationW(
                desktop, 2, buf2, length, ctypes.byref(length)
            )
            print(f"desktop: {buf2.value!r}", flush=True)
        except OSError as exc:
            print(f"window station query failed: {exc}", flush=True)
    import tkinter

    root = tkinter.Tk()
    root.withdraw()
    print(
        f"tcl {root.tk.call('info', 'patchlevel')} / "
        f"tk windowingsystem {root.tk.call('tk', 'windowingsystem')}",
        flush=True,
    )
    root.destroy()
    print("info: ok", flush=True)


# ---------------------------------------------------------------- win32

def _win32_roundtrip(text: str) -> str:
    import ctypes
    from ctypes import wintypes

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.GetClipboardData.argtypes = [wintypes.UINT]

    if not user32.OpenClipboard(None):
        raise RuntimeError(f"OpenClipboard failed ({ctypes.GetLastError()})")
    try:
        user32.EmptyClipboard()
        data = text.encode("utf-16-le") + b"\x00\x00"
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise RuntimeError(f"GlobalAlloc failed ({ctypes.GetLastError()})")
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            raise RuntimeError(f"GlobalLock failed ({ctypes.GetLastError()})")
        try:
            ctypes.memmove(ptr, data, len(data))
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            raise RuntimeError(f"SetClipboardData failed ({ctypes.GetLastError()})")
        got_handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not got_handle:
            raise RuntimeError(f"GetClipboardData empty ({ctypes.GetLastError()})")
        got_ptr = kernel32.GlobalLock(got_handle)
        if not got_ptr:
            raise RuntimeError(f"GlobalLock(read) failed ({ctypes.GetLastError()})")
        try:
            return ctypes.wstring_at(got_ptr)
        finally:
            kernel32.GlobalUnlock(got_handle)
    finally:
        user32.CloseClipboard()


def phase_win32() -> None:
    if sys.platform != "win32":
        print("win32: skipped (not Windows)", flush=True)
        return
    for i in range(100):
        text = f"probe-{i}-\u00e9\u2713"
        got = _win32_roundtrip(text)
        if got != text:
            raise AssertionError(f"iteration {i}: wrote {text!r}, read {got!r}")
        if i % 20 == 19:
            print(f"win32: {i + 1}/100 round-trips ok", flush=True)
    print("win32: ok (100/100 round-trips)", flush=True)


# ---------------------------------------------------------------- tk

def _tk_roundtrip(root, text: str) -> str:
    root.clipboard_clear()
    root.clipboard_append(text)
    via_api = root.clipboard_get()
    root.tk.call("clipboard", "clear")
    root.tk.call("clipboard", "append", text)
    via_tcl = str(root.tk.call("clipboard", "get"))
    if via_api != text or via_tcl != text:
        raise AssertionError(f"wrote {text!r}, api read {via_api!r}, tcl read {via_tcl!r}")
    return via_tcl


def phase_tk_basic() -> None:
    import tkinter

    root = tkinter.Tk()
    root.withdraw()
    try:
        for i in range(10):
            _tk_roundtrip(root, f"tk-basic-{i}")
            print(f"tk-basic: {i + 1}/10 round-trips ok", flush=True)
        print("tk-basic: ok (10/10 round-trips)", flush=True)
    finally:
        root.destroy()


def phase_tk_empty_get() -> None:
    import tkinter

    root = tkinter.Tk()
    root.withdraw()
    try:
        root.clipboard_clear()
        try:
            value = root.clipboard_get()
        except tkinter.TclError as exc:
            print(f"tk-empty-get: clean Tcl error as expected: {exc}", flush=True)
        else:
            print(f"tk-empty-get: get on empty returned {value!r} (no error)", flush=True)
        # the same through the raw Tcl path the failing tests use
        try:
            root.tk.call("clipboard", "get")
        except tkinter.TclError:
            print("tk-empty-get: raw tcl get raised cleanly too", flush=True)
        print("tk-empty-get: ok (error path did not fault)", flush=True)
    finally:
        root.destroy()


def phase_tk_stress() -> None:
    import tkinter

    root = None
    try:
        for i in range(200):
            if i % 20 == 0:
                if root is not None:
                    root.destroy()
                root = tkinter.Tk()
                root.withdraw()
            _tk_roundtrip(root, f"stress-{i}")
            if i % 20 == 19:
                print(f"tk-stress: {i + 1}/200 round-trips ok", flush=True)
        print("tk-stress: ok (200/200 round-trips across 10 roots)", flush=True)
    finally:
        if root is not None:
            root.destroy()


def phase_readonly_events() -> None:
    import tkinter

    for i in range(100):
        root = tkinter.Tk()
        root.withdraw()
        try:
            entry = tkinter.Entry(root)
            entry.insert(0, "untouched")
            entry.configure(state="readonly")
            text = tkinter.Text(root)
            text.insert("1.0", "untouched")
            text.configure(state="disabled")
            entry.grid(row=0, column=0)
            text.grid(row=1, column=0)
            root.update()

            # seed the clipboard exactly as the failing tests do
            entry.tk.call("clipboard", "clear")
            entry.tk.call("clipboard", "append", "pasted")

            for widget in (entry, text):
                widget.focus_force()
                root.update()
                if isinstance(widget, tkinter.Entry):
                    widget.selection_range(0, "end")
                else:
                    widget.tag_add("sel", "1.0", "end-1c")
                root.update()
                for seq in ("<<Copy>>", "<<Paste>>", "<<SelectAll>>"):
                    widget.event_generate(seq)
                    root.update()
                for keysym in ("a", "c", "v", "x"):
                    widget.event_generate(f"<Control-KeyPress-{keysym}>")
                    widget.event_generate(f"<Control-KeyRelease-{keysym}>")
                    root.update()
                for keysym in ("BackSpace", "Delete"):
                    widget.event_generate(f"<KeyPress-{keysym}>")
                    widget.event_generate(f"<KeyRelease-{keysym}>")
                    root.update()
                # read the clipboard back between widgets, as the tests do
                try:
                    entry.tk.call("clipboard", "get")
                except tkinter.TclError:
                    pass
            content_e = entry.get()
            content_t = text.get("1.0", "end-1c")
            if content_e != "untouched" or content_t != "untouched":
                raise AssertionError(
                    f"iteration {i}: read-only content changed: {content_e!r} {content_t!r}"
                )
        finally:
            root.destroy()
        if i % 10 == 9:
            print(f"readonly-events: {i + 1}/100 iterations ok", flush=True)
    print("readonly-events: ok (100/100 iterations)", flush=True)


PHASE_FUNCS = {
    "info": phase_info,
    "win32": phase_win32,
    "tk-basic": phase_tk_basic,
    "tk-empty-get": phase_tk_empty_get,
    "tk-stress": phase_tk_stress,
    "readonly-events": phase_readonly_events,
}


# ---------------------------------------------------------------- parent

def run_parent() -> int:
    import platform

    print(f"clipboard probe — {platform.platform()} — python {sys.version}\n", flush=True)
    failures = 0
    for phase in PHASES:
        if phase == "win32" and sys.platform != "win32":
            print(f"{phase:16s} --   skipped (not Windows)")
            continue
        repeats = 1 if phase == "info" else REPEATS
        for attempt in range(1, repeats + 1):
            proc = subprocess.run(
                [sys.executable, "-u", __file__, phase],
                capture_output=True,
                text=True,
                timeout=CHILD_TIMEOUT,
            )
            tail = "\n".join(
                line for line in (proc.stdout or "").strip().splitlines() if line
            )[-400:]
            if proc.returncode == 0:
                verdict = "ok"
            elif proc.returncode == ACCESS_VIOLATION or proc.returncode < 0:
                verdict = f"CRASH (exit {proc.returncode:#x})"
                failures += 1
            else:
                verdict = f"ERROR (exit {proc.returncode})"
                failures += 1
            print(f"{phase:16s} {attempt}/{repeats}   {verdict}", flush=True)
            if verdict != "ok":
                print(f"    last output: {tail}", flush=True)
                stderr_tail = (proc.stderr or "").strip()[-600:]
                if stderr_tail:
                    print(f"    stderr tail: {stderr_tail}", flush=True)
    print(
        "\nVERDICT: "
        + ("all phases clean — the session's clipboard is reliable at every level probed"
           if failures == 0
           else f"{failures} phase run(s) crashed or errored — see table above"),
        flush=True,
    )
    return 0 if failures == 0 else 1


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in PHASE_FUNCS:
        PHASE_FUNCS[sys.argv[1]]()
        return 0
    return run_parent()


if __name__ == "__main__":
    raise SystemExit(main())
