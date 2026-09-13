"""Read an Xvfb framebuffer directly, without spawning a screenshot process.

``Xvfb -fbdir DIR`` keeps its screen in ``DIR/Xvfb_screen0`` as a memory-mapped
XWD file, so the current contents of the display are a slice away. That matters
because the probe compares tens of thousands of renderings: ``xwd`` costs a fork
and an exec each time, this costs a memory read.

The reader is verified against ``xwd`` itself in :mod:`rules`.

Everything under ``ttk_style_probe`` runs on the Python that has ``tkinter``
built in, which on most systems is older than this project's floor. It keeps to
what a 3.11 interpreter accepts for that reason.
"""

import mmap
import struct
from types import TracebackType
from typing import Self

#: The 25 big-endian words an XWD file opens with, in order.
_HEADER_FIELDS = [
    "header_size", "file_version", "pixmap_format", "pixmap_depth", "pixmap_width",
    "pixmap_height", "xoffset", "byte_order", "bitmap_unit", "bitmap_bit_order",
    "bitmap_pad", "bits_per_pixel", "bytes_per_line", "visual_class", "red_mask",
    "green_mask", "blue_mask", "bits_per_rgb", "colormap_entries", "ncolors",
    "window_width", "window_height", "window_x", "window_y", "window_bdrwidth",
]  # fmt: skip


class Framebuffer:
    """The live screen of an Xvfb display, read through its backing file.

    Attributes:
        header: The XWD header fields, keyed by name.
        width: Screen width in pixels.
        height: Screen height in pixels.
        stride: Bytes per row, which exceeds ``width * 4`` when rows are padded.
    """

    def __init__(self, path: str) -> None:
        self._file = open(path, "rb")  # ruff: ignore[open-file-with-context-handler]  -- held for the mmap's lifetime
        self._map = mmap.mmap(self._file.fileno(), 0, access=mmap.ACCESS_READ)
        self.header = dict(zip(_HEADER_FIELDS, struct.unpack(">25I", self._map[:100]), strict=True))
        self.width = self.header["pixmap_width"]
        self.height = self.header["pixmap_height"]
        self.stride = self.header["bytes_per_line"]
        self.depth = self.header["bits_per_pixel"]
        self._offset = self.header["header_size"] + self.header["ncolors"] * 12

    def grab(self) -> bytes:
        """Return the whole screen's pixel bytes as they stand right now."""
        return self._map[self._offset : self._offset + self.stride * self.height]

    def region(self, x: int, y: int, width: int, height: int) -> bytes:
        """Return one rectangle's pixel bytes, clipped to the screen."""
        x, y = max(x, 0), max(y, 0)
        width = min(width, self.width - x)
        height = min(height, self.height - y)
        raw = self.grab()
        return b"".join(
            raw[(y + row) * self.stride + x * 4 : (y + row) * self.stride + (x + width) * 4]
            for row in range(height)
        )

    def close(self) -> None:
        """Release the mapping and the file behind it."""
        self._map.close()
        self._file.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def count_diff(a: bytes, b: bytes) -> int:
    """Return how many bytes differ between two equal-length grabs."""
    return sum(1 for x, y in zip(a, b, strict=False) if x != y)
