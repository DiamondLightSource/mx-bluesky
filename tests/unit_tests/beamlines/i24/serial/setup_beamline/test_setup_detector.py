from unittest.mock import patch

import pytest
from bluesky.run_engine import RunEngine
from dodal.devices.motors import YZStage
from ophyd_async.testing import set_mock_value

from mx_bluesky.beamlines.i24.serial.parameters.constants import SSXType
from mx_bluesky.beamlines.i24.serial.setup_beamline import Eiger
from mx_bluesky.beamlines.i24.serial.setup_beamline.setup_detector import (
    EXPT_TYPE_DETECTOR_PVS,
    DetRequest,
    _get_requested_detector,
    get_detector_type,
    setup_detector_stage,
)


def test_get_detector_type(RE, detector_stage: YZStage):
    set_mock_value(detector_stage.y.user_readback, -59)
    det_type = RE(get_detector_type(detector_stage)).plan_result
    assert det_type.name == "eiger"


@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_detector.caget")
def test_get_requested_detector(fake_caget):
    fake_caget.return_value = "0"
    assert _get_requested_detector("some_pv") == Eiger.name


@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_detector.caget")
def test_get_requested_detector_raises_error_for_invalid_value(fake_caget):
    fake_caget.return_value = "something"
    with pytest.raises(ValueError):
        _get_requested_detector("some_pv")


@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_detector.caget")
@patch("mx_bluesky.beamlines.i24.serial.setup_beamline.setup_detector.caput")
@pytest.mark.parametrize(
    "requested_detector_value, serial_type, detector_target",
    [
        (DetRequest.eiger.value, SSXType.FIXED, Eiger.det_y_target),
    ],
)
async def test_setup_detector_stage(
    fake_caput,
    fake_caget,
    requested_detector_value,
    serial_type,
    detector_target,
    detector_stage: YZStage,
    RE: RunEngine,
):
    fake_caget.return_value = requested_detector_value
    RE(setup_detector_stage(serial_type, detector_stage))
    fake_caput.assert_called_once_with(
        EXPT_TYPE_DETECTOR_PVS[serial_type],
        _get_requested_detector(requested_detector_value),
    )
    assert await detector_stage.y.user_setpoint.get_value() == detector_target
