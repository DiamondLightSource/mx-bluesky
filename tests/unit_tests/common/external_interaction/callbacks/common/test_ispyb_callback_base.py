from unittest.mock import MagicMock, call, patch

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
    run_engine: RunEngine, test_three_d_grid_params: SpecifiedThreeDGridScan
):
    test_visit = "test_visit"

    # BlueAPI does this when submitting a task
    run_engine.md.update({"instrument_session": test_visit})

    callback = BaseISPyBCallback()
    callback.activity_gated_stop = MagicMock()
    test_three_d_grid_params.visit = USE_NUMTRACKER
    callback.params = test_three_d_grid_params
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
    run_engine: RunEngine, test_three_d_grid_params: SpecifiedThreeDGridScan
):
    callback = BaseISPyBCallback()
    callback.activity_gated_stop = MagicMock()
    test_three_d_grid_params.visit = USE_NUMTRACKER
    callback.params = test_three_d_grid_params
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


def _get_working_doc():
    return {
        "data": {
            "flux-flux_reading": 0,
            "eiger-ispyb_detector_id": 0,
            "eiger_cam_roi_mode": None,
            "attenuator-actual_transmission": None,
        }
    }


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_callback_base.ISPYB_ZOCALO_CALLBACK_LOGGER"
)
def test_handle_ispyb_transmission_flux_read_if_no_beamsize_warning(
    mock_logger: MagicMock,
    test_three_d_grid_params: SpecifiedThreeDGridScan,
):
    callback = BaseISPyBCallback()
    callback.params = test_three_d_grid_params
    doc = _get_working_doc()
    callback._handle_ispyb_transmission_flux_read(doc)  # type: ignore
    mock_logger.warning.assert_has_calls(
        [call("ISPyB callbacks couldn't get beamsize")]
    )


@patch(
    "mx_bluesky.common.external_interaction.callbacks.common.ispyb_callback_base.ISPYB_ZOCALO_CALLBACK_LOGGER"
)
def test_handle_ispyb_transmission_flux_read_if_params_specify_beamsize(
    mock_logger: MagicMock,
    test_three_d_grid_params: SpecifiedThreeDGridScan,
):
    test_three_d_grid_params.beam_size_x = 0  # type: ignore
    test_three_d_grid_params.beam_size_y = 1  # type: ignore

    callback = BaseISPyBCallback()
    callback.params = test_three_d_grid_params
    doc = _get_working_doc()
    callback._handle_ispyb_transmission_flux_read(doc)  # type: ignore

    assert (
        call("ISPyB callbacks couldn't get beamsize")
        not in mock_logger.warning.call_args_list
    )
