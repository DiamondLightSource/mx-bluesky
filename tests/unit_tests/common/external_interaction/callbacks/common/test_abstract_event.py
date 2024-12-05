import dataclasses

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.run_engine import RunEngine

from mx_bluesky.common.external_interaction.callbacks.common.abstract_event import (
    AbstractEvent,
)


@dataclasses.dataclass(frozen=True)
class MyEvent(AbstractEvent):
    my_int: int
    my_float: float
    my_string: str
    my_bool: bool


def test_can_create_and_raise_an_event(RE: RunEngine):
    @bpp.run_decorator()
    def fire_an_event():
        yield from bps.create("MY_EVENT")
        yield from bps.read(
            MyEvent(my_int=123, my_float=1.234, my_string="Test message", my_bool=True)
        )
        yield from bps.save()

    the_event = None

    def my_event_handler(name: str, doc: dict):
        nonlocal the_event
        the_event = doc

    RE.subscribe(my_event_handler, "event")
    RE(fire_an_event())

    assert the_event
    assert the_event["data"] == {
        "my_bool": True,
        "my_float": 1.234,
        "my_string": "Test message",
        "my_int": 123,
    }
