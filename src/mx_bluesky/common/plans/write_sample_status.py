import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import pydantic
from blueapi.core import BlueskyContext

from mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback import (
    SampleHandlingCallback,
)
from mx_bluesky.common.parameters.components import MxBlueskyParameters
from mx_bluesky.common.utils.exceptions import SampleException
from mx_bluesky.hyperion.utils.context import device_composite_from_context

callback = SampleHandlingCallback()


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class WriteSampleStatus(MxBlueskyParameters):
    """Composite that provides access to the required devices."""


def create_devices(context: BlueskyContext) -> WriteSampleStatus:
    """Create the necessary devices for the plan."""
    return device_composite_from_context(context, WriteSampleStatus)


@bpp.subs_decorator(callback)
def deposit_sample_error(exception_type, sample_id):
    @bpp.run_decorator(
        md={
            "metadata": {"sample_id": sample_id},
            "activate_callbacks": ["SampleHandlingCallback"],
        }
    )
    def _inner():
        if exception_type == "Beamline":
            raise AssertionError()
        elif exception_type == "Sample":
            raise SampleException
        yield from bps.null()

    yield from _inner()


@bpp.subs_decorator(callback)
def deposit_loaded_sample(sample_id):
    @bpp.run_decorator(
        md={
            "metadata": {"sample_id": sample_id},
            "activate_callbacks": ["SampleHandlingCallback"],
        }
    )
    def _inner():
        yield from bps.null()

    yield from _inner()
