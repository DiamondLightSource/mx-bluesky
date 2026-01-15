from unittest.mock import MagicMock

import bluesky.preprocessors as bpp
import pytest
from bluesky import plan_stubs as bps
from bluesky.run_engine import RunEngine

from mx_bluesky.common.external_interaction.callbacks.common.ispyb_callback_base import (
    BaseISPyBCallback,
)
from mx_bluesky.common.parameters.constants import USE_NUMTRACKER
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan


def test_visit_extracted_from_numtracker(
    run_engine: RunEngine, test_fgs_params: SpecifiedThreeDGridScan
):
    test_visit = "test_visit"

    # BlueAPI does this when submitting a task
    run_engine.md.update({"instrument_session": test_visit})

    callback = BaseISPyBCallback()
    callback.activity_gated_stop = MagicMock()
    test_fgs_params.visit = USE_NUMTRACKER
    callback.params = test_fgs_params
    run_engine.subscribe(callback)

    @bpp.run_decorator(
        md={
            "activate_callbacks": ["BaseISPyBCallback"],
        },
    )
    def test_plan():
        yield from bps.null()

    run_engine(test_plan())

    assert callback.params.visit == test_visit


def test_exception_when_instrument_session_doesnt_exist(
    run_engine: RunEngine, test_fgs_params: SpecifiedThreeDGridScan
):
    callback = BaseISPyBCallback()
    callback.activity_gated_stop = MagicMock()
    test_fgs_params.visit = USE_NUMTRACKER
    callback.params = test_fgs_params
    run_engine.subscribe(callback)

    @bpp.run_decorator(
        md={
            "activate_callbacks": ["BaseISPyBCallback"],
        },
    )
    def test_plan():
        yield from bps.null()

    with pytest.raises(ValueError):
        run_engine(test_plan())
