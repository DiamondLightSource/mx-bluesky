import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp

from mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback import (
    SampleHandlingCallback,
)
from mx_bluesky.common.utils.exceptions import SampleException

callback = SampleHandlingCallback()


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
