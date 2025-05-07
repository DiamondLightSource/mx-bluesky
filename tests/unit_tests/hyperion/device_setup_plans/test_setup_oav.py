from unittest.mock import MagicMock

import pytest
from bluesky import plan_stubs as bps
from bluesky.run_engine import RunEngine
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.oav.pin_image_recognition import PinTipDetection
from ophyd.status import Status
from ophyd_async.sim import SimMotor

from mx_bluesky.common.device_setup_plans.setup_oav import (
    pre_centring_setup_oav,
)

OAV_CENTRING_JSON = "tests/test_data/test_OAVCentring.json"


@pytest.fixture
def mock_parameters():
    return OAVParameters("loopCentring", OAV_CENTRING_JSON)


def test_when_set_up_oav_then_only_waits_on_oav_to_finish(
    mock_parameters: OAVParameters, oav: OAV, ophyd_pin_tip_detection: PinTipDetection
):
    """This test will hang if pre_centring_setup_oav waits too generally as my_waiting_device
    never finishes moving"""
    my_waiting_device = SimMotor(name="")
    my_waiting_device.set = MagicMock(return_value=Status())

    def my_plan():
        yield from bps.abs_set(my_waiting_device, 10, wait=False)
        yield from pre_centring_setup_oav(oav, mock_parameters, ophyd_pin_tip_detection)

    RE = RunEngine()
    RE(my_plan())
