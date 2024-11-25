import builtins
import dataclasses
import time
from abc import ABC
from typing import Literal

from bluesky.protocols import Readable, Reading
from event_model import DataKey


@dataclasses.dataclass(frozen=True)
class AbstractEvent(Readable, ABC):
    """An abstract superclass that can be extended to provide lightweight software events
    for bluesky plans, without having to incur the overhead of creating ophyd-async devices
    specifically for the purpose.

    The currently supported types for field annotations in the event are ``str``, ``int``, ``float``, ``bool``

    In future array types may be supported.

    Examples:
        Subclasses should extend this class and decorate with::

            @dataclasses.dataclass(frozen=True)

        To raise an event, simply construct the event and then ``read`` it as you would a device::

            yield from bps.create("MY_EVENT_NAME")
            my_event = MyEvent(an_int=1)
            yield from bps.read(my_event)
            yield from bps.save()
    """

    def read(self) -> dict[str, Reading]:
        return {
            f.name: AbstractEvent._reading_from_value(getattr(self, f.name))
            for f in dataclasses.fields(self)
        }

    def describe(self) -> dict[str, DataKey]:
        return {
            f.name: DataKey(dtype=AbstractEvent._dtype_of(f.type), shape=[], source="")
            for f in dataclasses.fields(self)
        }

    @classmethod
    def _reading_from_value(cls, value):
        return Reading(timestamp=time.time(), value=value)

    @classmethod
    def _dtype_of(cls, t) -> Literal["string", "number", "boolean", "integer"]:
        match t:
            case builtins.str:
                return "string"
            case builtins.bool:
                return "boolean"
            case builtins.int:
                return "integer"
            case builtins.float:
                return "number"
        # TODO array support
        raise ValueError(f"Unsupported type for AbstractEvent: {t}")

    @property
    def name(self) -> str:
        return type(self).__name__
