"""The subscription handle both notification routes hand back.

One type for the whole library: an observable's ``watch`` returns one,
and the events interface's registration routes return the same type.
"""

from collections.abc import Callable


class Subscription:
    """A registration's handle: cancel it, or ask whether it still stands.

    Cancelling is idempotent and final — a cancelled subscription never
    delivers again and cannot be revived; register anew instead.
    """

    __slots__ = ("_cancel",)

    def __init__(self, cancel: Callable[[], None], /) -> None:
        """Wrap the registration's own teardown.

        Args:
            cancel (Callable[[], None]): The registrar's teardown for
                this one registration; called at most once.
        """
        self._cancel: Callable[[], None] | None = cancel

    @property
    def active(self) -> bool:
        """Whether the registration still stands and can deliver."""
        return self._cancel is not None

    def cancel(self) -> None:
        """End the registration; harmless on one already cancelled."""
        teardown = self._cancel
        self._cancel = None
        if teardown is not None:
            teardown()
