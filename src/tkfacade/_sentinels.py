from enum import Enum
from typing import Final, Literal


class _Sentinel(Enum):
    OMIT = "OMIT"


OMIT: Final = _Sentinel.OMIT

type Omitted = Literal[_Sentinel.OMIT]
