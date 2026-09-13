"""The frame containers: a plain one to build in, and the card stacks.

:class:`Frame` is the ordinary themed container — it holds whatever is
created inside it, pads it, and is placed as one unit; nothing more.
:class:`StackFrame` and :class:`TabFrame` give one region several pages
addressed by key with exactly one mapped at a time, and differ in how
the pages are hosted and who may switch them.
"""

from ._abstract import AbstractMultiFrame as AbstractMultiFrame
from ._frame import Frame as Frame
from ._labelframe import LabelFrame as LabelFrame
from ._paned import PanedFrame as PanedFrame
from ._stack import StackFrame as StackFrame
from ._tab import TabFrame as TabFrame
