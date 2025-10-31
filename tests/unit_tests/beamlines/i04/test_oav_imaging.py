from unittest.mock import patch

import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.mx_phase1.beamstop import Beamstop, BeamstopPositions
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.robot import BartRobot, PinMounted
from dodal.devices.scintillator import InOut, Scintillator
from dodal.devices.zebra.zebra_controlled_shutter import (
    ZebraShutter,
    ZebraShutterControl,
    ZebraShutterState,
)
from ophyd_async.testing import set_mock_value

from mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging import (
    optimise_oav_transmission_binary_search,
    take_and_save_oav_image,
    take_oav_image_with_scintillator_in,
)
from mx_bluesky.common.utils.exceptions import BeamlineStateException


async def test_check_exception_raised_if_pin_mounted(
    RE: RunEngine,
    robot: BartRobot,
    beamstop: Beamstop,
    scintillator: Scintillator,
    attenuator: BinaryFilterAttenuator,
    shutter: ZebraShutter,
    oav: OAV,
):
    set_mock_value(robot.gonio_pin_sensor, PinMounted.NO_PIN_MOUNTED)

    with pytest.raises(BeamlineStateException, match="Pin should not be mounted!"):
        RE(
            take_oav_image_with_scintillator_in(
                robot=robot,
                beamstop=beamstop,
                scintillator=scintillator,
                attenuator=attenuator,
                shutter=shutter,
                oav=oav,
            )
        )


def test_plan_stubs_called_in_correct_order(
    sim_run_engine: RunEngineSimulator,
    robot: BartRobot,
    beamstop: Beamstop,
    scintillator: Scintillator,
    attenuator: BinaryFilterAttenuator,
    shutter: ZebraShutter,
    oav: OAV,
):
    messages = sim_run_engine.simulate_plan(
        take_oav_image_with_scintillator_in(
            robot=robot,
            beamstop=beamstop,
            scintillator=scintillator,
            attenuator=attenuator,
            shutter=shutter,
            oav=oav,
        )
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "read" and msg.obj.name == "robot-gonio_pin_sensor",
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "beamstop-selected_pos"
        and msg.args[0] == BeamstopPositions.DATA_COLLECTION
        and msg.kwargs["group"] == "Wait for scint to move in",
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "scintillator-selected_pos"
        and msg.args[0] == InOut.IN
        and msg.kwargs["group"] == "Wait for scint to move in",
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "attenuator"
        and msg.args[0] == 1,
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "wait",
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "sample_shutter-control_mode"
        and msg.args[0] == ZebraShutterControl.MANUAL,
        # and msg.args[1] is True,
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "sample_shutter"
        and msg.args[0] == ZebraShutterState.OPEN,
        # and msg.kwargs["wait"] == True
    )


def test_oav_image(
    sim_run_engine: RunEngineSimulator, oav: OAV, path=".", name="mock-name"
):
    messages = sim_run_engine.simulate_plan(
        take_and_save_oav_image(oav=oav, file_path=path, file_name=name)
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "oav-snapshot-filename"
        and msg.args[0] == "mock-name"
        and msg.kwargs["group"] == "path setting",
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "oav-snapshot-directory"
        and msg.args[0] == "."
        and msg.kwargs["group"] == "path setting",
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "wait",
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "trigger" and msg.obj.name == "oav-snapshot",
    )


def test_optimise_oav_transmission_binary_search():
    # Simulated transmission-to-pixel mapping
    # expecting transmission 18.75 to be correct
    transmission_map = {100: 255, 50: 180, 25: 160, 18.75: 130, 12.5: 118, 0: 0}

    # now defining a mock function
    def mock_get_max_pixel_value_from_transmission(transmission):
        pixel_val = transmission_map.get(transmission)

        if pixel_val is None:
            raise KeyError(f"Transmission {transmission} is not in the mock dictionary")

        return pixel_val

    with patch(
        "mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging.get_max_pixel_value_from_transmission",
        side_effect=mock_get_max_pixel_value_from_transmission,
    ):
        result = optimise_oav_transmission_binary_search(255 / 2, 100, 0, 5, 10)
        assert result == 18.75
