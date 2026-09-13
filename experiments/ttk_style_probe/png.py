"""Write framebuffer grabs out as PNGs, so a verdict can be checked by eye.

A pixel comparison says that a rendering changed, never that it changed the way
it was supposed to. Every surprising verdict in this directory's results was
confirmed against a picture written by this module.

Pillow would do the job, but the probe is otherwise dependency-free and runs
against a bare system Python that has ``tkinter`` and nothing else.
"""

import struct
import zlib


def write_png(path: str, pixels: bytes, width: int, height: int, stride: int) -> None:
    """Write BGRX framebuffer bytes to ``path`` as an 8-bit RGB PNG.

    Args:
        path: Destination file.
        pixels: Raw framebuffer bytes, four bytes per pixel, blue first.
        width: Image width in pixels.
        height: Image height in pixels.
        stride: Bytes per row in ``pixels``, padding included.
    """
    rows = bytearray()
    for y in range(height):
        rows.append(0)  # per-row filter type: none
        row = pixels[y * stride : y * stride + width * 4]
        for x in range(width):
            blue, green, red = row[x * 4], row[x * 4 + 1], row[x * 4 + 2]
            rows += bytes((red, green, blue))

    def chunk(tag: bytes, data: bytes) -> bytes:
        head = struct.pack(">I", len(data)) + tag + data
        return head + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(chunk(b"IHDR", header))
        fh.write(chunk(b"IDAT", zlib.compress(bytes(rows), 6)))
        fh.write(chunk(b"IEND", b""))
