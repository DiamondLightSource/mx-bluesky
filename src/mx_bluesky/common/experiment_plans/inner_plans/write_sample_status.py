from enum import StrEnum

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp

from mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback import (
    SampleHandlingCallback,
)
from mx_bluesky.common.utils.exceptions import SampleException


class SampleStatusExceptionType(StrEnum):
    BEAMLINE = "Beamline"
    SAMPLE = "Sample"


@bpp.subs_decorator(SampleHandlingCallback())
def deposit_sample_error(exception_type: SampleStatusExceptionType, sample_id: int):
    @bpp.run_decorator(
        md={
            "metadata": {"sample_id": sample_id},
            "activate_callbacks": ["SampleHandlingCallback"],
        }
    )
    def _inner():
        yield from bps.null()
        if exception_type == SampleStatusExceptionType.BEAMLINE:
            raise AssertionError()
        elif exception_type == SampleStatusExceptionType.SAMPLE:
            raise SampleException

    yield from _inner()


@bpp.subs_decorator(SampleHandlingCallback(record_loaded_on_success=True))
def deposit_loaded_sample(sample_id: int):
    @bpp.run_decorator(
        md={
            "metadata": {"sample_id": sample_id},
            "activate_callbacks": ["SampleHandlingCallback"],
        }
    )
    def _inner():
        yield from bps.null()

    yield from _inner()
