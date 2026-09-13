import tkinter as tk
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class StackEntry:
    depth: int  # 0 == bottom of the stack
    name: str  # Tk path name, e.g. '.container.!frame2'
    cls: str
    parent: str
    manager: str  # 'grid', 'place', 'pack', or '' if unmanaged
    mapped: bool
    cell: tuple[str, str] | None  # (row, column) when gridded
    sticky: str
    managed_in: str  # the widget grid actually placed it into
    geometry: tuple[int, int, int, int]  # x, y, w, h


def stacking_order(master: tk.Misc) -> list[StackEntry]:
    master.update_idletasks()  # geometry/mapped are stale before this
    entries: list[StackEntry] = []
    for depth, child in enumerate(master.winfo_children()):
        manager = child.winfo_manager()
        info: dict[str, Any] = (
            dict(child.grid_info()) if isinstance(child, tk.Widget) and manager == "grid" else {}
        )
        cell = (str(info["row"]), str(info["column"])) if info else None
        container = info.get("in")
        entries.append(
            StackEntry(
                depth=depth,
                name=str(child),
                cls=child.winfo_class(),
                parent=child.winfo_parent(),
                manager=manager,
                mapped=child.winfo_ismapped(),
                cell=cell,
                sticky=str(info.get("sticky", "")),
                managed_in=str(container) if container is not None else "",
                geometry=(
                    child.winfo_x(),
                    child.winfo_y(),
                    child.winfo_width(),
                    child.winfo_height(),
                ),
            )
        )
    return entries


def print_stack(master: tk.Misc, label: str = "") -> None:
    if label:
        print(f"--- {label} ---")
    for e in stacking_order(master):
        print(
            f"[{e.depth}] {e.name:<28} {e.cls:<10} mgr={e.manager or '-':<6} "
            f"mapped={e.mapped!s:<5} cell={e.cell} sticky={e.sticky or '-':<5} "
            f"in={e.managed_in} parent={e.parent} geom={e.geometry}"
        )
