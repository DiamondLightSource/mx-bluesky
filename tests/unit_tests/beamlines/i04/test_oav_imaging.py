from unittest.mock import MagicMock, patch

import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.mx_phase1.beamstop import Beamstop, BeamstopPositions
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.robot import BartRobot, PinMounted
from dodal.devices.scintillator import InOut, Scintillator
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra_controlled_shutter import (
    ZebraShutter,
    ZebraShutterControl,
    ZebraShutterState,
)
from ophyd_async.core import set_mock_value

from mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging import (
    _prepare_beamline_for_scintillator_images,
    take_and_save_oav_image,
    take_oav_image_with_scintillator_in,
)
from mx_bluesky.common.utils.exceptions import BeamlineStateError


async def test_check_exception_raised_if_pin_mounted(
    run_engine: RunEngine,
    robot: BartRobot,
    beamstop_phase1: Beamstop,
    scintillator: Scintillator,
    attenuator: BinaryFilterAttenuator,
    sample_shutter: ZebraShutter,
    oav: OAV,
):
    set_mock_value(robot.gonio_pin_sensor, PinMounted.PIN_MOUNTED)

    with pytest.raises(BeamlineStateError, match="Pin should not be mounted!"):
        run_engine(
            take_oav_image_with_scintillator_in(
                robot=robot,
                beamstop=beamstop_phase1,
                scintillator=scintillator,
                attenuator=attenuator,
                shutter=sample_shutter,
                oav=oav,
            )
        )


def test_prepare_beamline_for_scint_images(
    sim_run_engine: RunEngineSimulator,
    robot: BartRobot,
    beamstop_phase1: Beamstop,
    backlight: Backlight,
    scintillator: Scintillator,
    xbpm_feedback: XBPMFeedback,
):
    test_group = "my_group"
    messages = sim_run_engine.simulate_plan(
        _prepare_beamline_for_scintillator_images(
            robot, beamstop_phase1, backlight, scintillator, xbpm_feedback, test_group
        )
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "read" and msg.obj.name == "robot-gonio_pin_sensor",
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "trigger" and msg.obj.name == "xbpm_feedback",
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "beamstop-selected_pos"
        and msg.args[0] == BeamstopPositions.DATA_COLLECTION
        and msg.kwargs["group"] == test_group,
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "backlight"
        and msg.args[0] == InOut.OUT,
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "scintillator-selected_pos"
        and msg.args[0] == InOut.IN
        and msg.kwargs["group"] == test_group,
    )


def test_plan_stubs_called_in_correct_order(
    sim_run_engine: RunEngineSimulator,
    robot: BartRobot,
    beamstop_phase1: Beamstop,
    scintillator: Scintillator,
    attenuator: BinaryFilterAttenuator,
    oav: OAV,
    sample_shutter: ZebraShutter,
    backlight: Backlight,
    xbpm_feedback: XBPMFeedback,
):
    messages = sim_run_engine.simulate_plan(
        take_oav_image_with_scintillator_in(
            attenuator=attenuator,
            shutter=sample_shutter,
            oav=oav,
            robot=robot,
            beamstop=beamstop_phase1,
            backlight=backlight,
            scintillator=scintillator,
            xbpm_feedback=xbpm_feedback,
        )
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
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == messages[0].kwargs["group"],
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "sample_shutter"
        and msg.args[0] == ZebraShutterState.OPEN,
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == messages[0].kwargs["group"],
    )


@pytest.mark.parametrize(
    "transmission",
    [1, 0.5, 0.1],
)
def test_plan_called_with_specified_transmission_then_transmission_set(
    sim_run_engine: RunEngineSimulator,
    robot: BartRobot,
    beamstop_phase1: Beamstop,
    scintillator: Scintillator,
    attenuator: BinaryFilterAttenuator,
    oav: OAV,
    sample_shutter: ZebraShutter,
    backlight: Backlight,
    xbpm_feedback: XBPMFeedback,
    transmission: float,
):
    messages = sim_run_engine.simulate_plan(
        take_oav_image_with_scintillator_in(
            transmission=transmission,
            attenuator=attenuator,
            shutter=sample_shutter,
            oav=oav,
            robot=robot,
            beamstop=beamstop_phase1,
            backlight=backlight,
            scintillator=scintillator,
            xbpm_feedback=xbpm_feedback,
        )
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "attenuator"
        and msg.args[0] == transmission,
    )


def test_oav_image(sim_run_engine: RunEngineSimulator, oav: OAV):
    mock_filepath = "mock_path"
    mock_filename = "mock_file"
    messages = sim_run_engine.simulate_plan(
        take_and_save_oav_image(mock_filename, mock_filepath, oav)
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "oav-snapshot-filename"
        and msg.args[0] == mock_filename,
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "set"
        and msg.obj.name == "oav-snapshot-directory"
        and msg.args[0] == mock_filepath,
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "wait",
    )

    messages = assert_message_and_return_remaining(
        messages,
        lambda msg: msg.command == "trigger" and msg.obj.name == "oav-snapshot",
    )


@patch(
    "mx_bluesky.beamlines.i04.oav_centering_plans.oav_imaging.os.path.exists",
    MagicMock(return_value=True),
)
def test_given_file_exists_then_take_oav_image_raises(
    sim_run_engine: RunEngineSimulator, oav: OAV
):
    with pytest.raises(FileExistsError):
        sim_run_engine.simulate_plan(
            take_and_save_oav_image("mock_file", "mock_path", oav)
        )


async def test_take_and_save_oav_image_in_re(run_engine: RunEngine, oav: OAV, tmp_path):
    expected_filename = "filename"
    expected_directory = str(tmp_path)
    run_engine(take_and_save_oav_image(expected_filename, expected_directory, oav))
    assert await oav.snapshot.filename.get_value() == expected_filename
    assert await oav.snapshot.directory.get_value() == str(expected_directory)
    oav.snapshot.trigger.assert_called_once()  # type: ignore
