from enum import StrEnum

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import pydantic
from blueapi.core import BlueskyContext
from pydantic_extra_types.semantic_version import SemanticVersion

from mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback import (
    SampleHandlingCallback,
)
from mx_bluesky.common.parameters.components import (
    PARAMETER_VERSION,
)
from mx_bluesky.common.parameters.write_sample_status import (
    WriteSampleLoaded,
    WriteSampleStatus,
)
from mx_bluesky.common.utils.context import device_composite_from_context
from mx_bluesky.common.utils.exceptions import SampleException

callback = SampleHandlingCallback()


class SampleStatusExceptionType(StrEnum):
    BEAMLINE = "Beamline"
    SAMPLE = "Sample"


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class NullDeviceComposite:
    pass


def create_devices(context: BlueskyContext) -> NullDeviceComposite:
    """Create the necessary devices for the plan."""
    return device_composite_from_context(context, NullDeviceComposite)


def deposit_sample_error_no_internal_callbacks(
    composite: NullDeviceComposite, params: WriteSampleStatus
):
    """Hyperion subscribes to external callbacks on instantiation, so needs an entry point without internal callbacks"""

    @bpp.run_decorator(
        md={
            "metadata": {"sample_id": params.sample_id},
            "activate_callbacks": ["SampleHandlingCallback"],
        }
    )
    def _inner():
        if params.exception_type == SampleStatusExceptionType.BEAMLINE:
            raise AssertionError()
        elif params.exception_type == SampleStatusExceptionType.SAMPLE:
            raise SampleException
        yield from bps.null()

    yield from _inner()


def deposit_loaded_sample_no_internal_callbacks(
    composite: NullDeviceComposite, params: WriteSampleLoaded
):
    """Hyperion subscribes to external callbacks on instantiation, so needs an entry point without internal callbacks"""

    @bpp.run_decorator(
        md={
            "metadata": {"sample_id": params.sample_id},
            "activate_callbacks": ["SampleHandlingCallback"],
        }
    )
    def _inner():
        yield from bps.null()

    yield from _inner()


@bpp.subs_decorator(callback)
def deposit_sample_error(exception_type: SampleStatusExceptionType, sample_id: int):
    """Entry point for BlueAPI. Creates a device composite and parameter model so that it is compatible with the Hyperion entry point for this plan"""

    params = WriteSampleStatus(
        sample_id=sample_id,
        exception_type=exception_type,
        parameter_model_version=SemanticVersion(major=PARAMETER_VERSION.major),
    )
    composite = NullDeviceComposite()

    yield from deposit_sample_error_no_internal_callbacks(composite, params)


@bpp.subs_decorator(callback)
def deposit_loaded_sample(sample_id: int):
    """Entry point for BlueAPI. Creates a device composite and parameter model so that it is compatible with the Hyperion entry point for this plan"""

    params = WriteSampleLoaded(
        sample_id=sample_id,
        parameter_model_version=SemanticVersion(major=PARAMETER_VERSION.major),
    )
    composite = NullDeviceComposite()
    yield from deposit_loaded_sample_no_internal_callbacks(composite, params)
