from contextlib import nullcontext
from unittest.mock import ANY, MagicMock, patch

import pytest
from bluesky import Msg
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.collimation_table import CollimationTable
from dodal.devices.cryostream import (
    CryoStreamGantry,
    CryoStreamSelection,
    OxfordCryoJet,
    OxfordCryoStream,
)
from dodal.devices.cryostream import InOut as CryoInOut
from dodal.devices.fluorescence_detector_motion import FluorescenceDetector
from dodal.devices.fluorescence_detector_motion import InOut as FlouInOut
from dodal.devices.hutch_shutter import HutchShutter, ShutterDemand
from dodal.devices.mx_phase1.beamstop import BeamstopPositions
from dodal.devices.robot import PinMounted
from dodal.devices.scintillator import InOut, Scintillator
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutterState
from ophyd_async.core import Signal, init_devices, set_mock_value
from ophyd_async.epics.motor import Motor

from mx_bluesky.hyperion.experiment_plans.udc_default_state import (
    CryoStreamError,
    UDCDefaultDevices,
    UnexpectedSampleError,
    move_to_udc_default_state,
)
from mx_bluesky.hyperion.parameters.constants import CONST, HyperionFeatureSettings


@pytest.fixture
async def cryostream_gantry(sim_run_engine: RunEngineSimulator):
    async with init_devices(mock=True):
        cryostream_gantry = CryoStreamGantry("")

    set_mock_value(cryostream_gantry.cryostream_selector, CryoStreamSelection.CRYOJET)
    set_mock_value(cryostream_gantry.cryostream_selected, 1)
    sim_run_engine.add_read_handler_for(
        cryostream_gantry.cryostream_selector, CryoStreamSelection.CRYOJET
    )
    sim_run_engine.add_read_handler_for(cryostream_gantry.cryostream_selected, 1)
    yield cryostream_gantry


@pytest.fixture
async def default_devices(
    beamstop_check_devices,
    cryostream_gantry,
    robot,
    smargon,
    sim_run_engine,
    run_engine,
):
    async with init_devices(mock=True):
        cryostream = OxfordCryoStream("")
        cryojet = OxfordCryoJet("")
        fluo = FluorescenceDetector("")
        hutch_shutter = HutchShutter("")
        scintillator = Scintillator("", MagicMock(), MagicMock(), name="scin")
        collimation_table = CollimationTable("")

    with patch("dodal.devices.hutch_shutter.TEST_MODE", True):
        devices = UDCDefaultDevices(
            collimation_table=collimation_table,
            cryostream=cryostream,
            cryojet=cryojet,
            cryostream_gantry=cryostream_gantry,
            fluorescence_det_motion=fluo,
            hutch_shutter=hutch_shutter,
            robot=robot,
            scintillator=scintillator,
            smargon=smargon,
            **beamstop_check_devices.__dict__,
        )
        sim_run_engine.add_read_handler_for(
            devices.robot.gonio_pin_sensor, PinMounted.NO_PIN_MOUNTED
        )

        yield devices


@pytest.fixture
def feature_flags_with_beamstop_diode_check():
    with patch(
        "mx_bluesky.hyperion.experiment_plans.udc_default_state.get_hyperion_config_client"
    ) as mock_get_config_client:
        mock_get_config_client.return_value.get_feature_flags.return_value = (
            HyperionFeatureSettings(
                BEAMSTOP_DIODE_CHECK=True,
            )
        )
        yield mock_get_config_client.return_value.get_feature_flags.return_value


async def test_given_cryostream_temp_is_too_high_then_exception_raised(
    sim_run_engine: RunEngineSimulator,
    default_devices: UDCDefaultDevices,
):
    sim_run_engine.add_read_handler_for(
        default_devices.cryostream.temp,
        CONST.HARDWARE.MAX_CRYO_TEMP_K + 10,
    )
    with pytest.raises(CryoStreamError, match="temperature is too high"):
        sim_run_engine.simulate_plan(move_to_udc_default_state(default_devices))


async def test_given_cryostream_pressure_is_too_high_then_exception_raised(
    sim_run_engine: RunEngineSimulator,
    default_devices: UDCDefaultDevices,
):
    sim_run_engine.add_read_handler_for(
        default_devices.cryostream.back_pressure,
        CONST.HARDWARE.MAX_CRYO_PRESSURE_BAR + 10,
    )
    with pytest.raises(CryoStreamError, match="pressure is too high"):
        sim_run_engine.simulate_plan(move_to_udc_default_state(default_devices))


async def test_scintillator_is_moved_out_before_aperture_scatterguard_moved_in(
    sim_run_engine: RunEngineSimulator,
    default_devices: UDCDefaultDevices,
):
    msgs = sim_run_engine.simulate_plan(move_to_udc_default_state(default_devices))

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "scin-selected_pos"
        and msg.args[0] == InOut.OUT,
    )
    msgs = assert_message_and_return_remaining(msgs, lambda msg: msg.command == "wait")
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "aperture_scatterguard-selected_aperture"
        and msg.args[0] == ApertureValue.SMALL,
    )


def test_udc_default_state_runs_in_real_run_engine(
    run_engine: RunEngine, default_devices: UDCDefaultDevices
):
    set_mock_value(default_devices.cryostream.temp, 100)
    set_mock_value(default_devices.cryostream.back_pressure, 0.01)
    default_devices.scintillator._aperture_scatterguard().selected_aperture.get_value = MagicMock(
        return_value=ApertureValue.PARKED
    )

    run_engine(move_to_udc_default_state(default_devices))


def test_beamstop_moved_to_data_collection_if_diode_check_not_enabled(
    sim_run_engine: RunEngineSimulator,
    default_devices: UDCDefaultDevices,
):
    pre_beamstop_group = "pre_beamstop_check"
    msgs = sim_run_engine.simulate_plan(move_to_udc_default_state(default_devices))
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait" and msg.kwargs["group"] == pre_beamstop_group,
    )
    assert (
        msgs[1].command == "set"
        and msgs[1].obj is default_devices.beamstop.selected_pos
        and msgs[1].args[0] == BeamstopPositions.DATA_COLLECTION
    )
    assert (
        msgs[2].command == "wait" and msgs[2].kwargs["group"] == msgs[1].kwargs["group"]
    )


@pytest.mark.parametrize(
    "min_z, max_z",
    [
        [250, 800],
        [300, 650],
    ],
)
@patch(
    "mx_bluesky.hyperion.experiment_plans.udc_default_state.move_beamstop_in_and_verify_using_diode",
    return_value=iter([Msg("move_beamstop_in")]),
)
def test_beamstop_check_is_called_with_detector_distances_from_config_server(
    mock_move_beamstop_in: MagicMock,
    default_devices: UDCDefaultDevices,
    sim_run_engine: RunEngineSimulator,
    min_z: float,
    max_z: float,
):
    with patch(
        "mx_bluesky.hyperion.experiment_plans.udc_default_state.get_hyperion_config_client"
    ) as mock_get_config_client:
        mock_get_config_client.return_value.get_feature_flags.return_value = (
            HyperionFeatureSettings(
                BEAMSTOP_DIODE_CHECK=True,
                DETECTOR_DISTANCE_LIMIT_MAX_MM=max_z,
                DETECTOR_DISTANCE_LIMIT_MIN_MM=min_z,
            )
        )
        sim_run_engine.simulate_plan(move_to_udc_default_state(default_devices))
    mock_move_beamstop_in.assert_called_once_with(ANY, ANY, min_z, max_z)


@patch(
    "mx_bluesky.hyperion.experiment_plans.udc_default_state.move_beamstop_in_and_verify_using_diode",
    MagicMock(return_value=iter([Msg("move_beamstop_in")])),
)
def test_udc_pre_and_post_groups_contains_expected_items_and_are_waited_on_before_and_after_beamstop_check(
    sim_run_engine: RunEngineSimulator,
    default_devices: UDCDefaultDevices,
    feature_flags_with_beamstop_diode_check: HyperionFeatureSettings,
):
    msgs = sim_run_engine.simulate_plan(move_to_udc_default_state(default_devices))

    pre_beamstop_group = "pre_beamstop_check"
    post_beamstop_group = "post_beamstop_check"

    def assert_expected_set(signal: Signal | Motor, value, group):
        return assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "set"
            and msg.obj.name == signal.name
            and msg.args[0] == value
            and msg.kwargs["group"] == group,
        )

    msgs = assert_expected_set(
        default_devices.fluorescence_det_motion.pos, FlouInOut.OUT, pre_beamstop_group
    )
    coll = default_devices.collimation_table
    for device in [
        coll.inboard_y,
        coll.outboard_y,
        coll.upstream_y,
        coll.upstream_x,
        coll.downstream_x,
    ]:
        msgs = assert_expected_set(device, 0, pre_beamstop_group)

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait" and msg.kwargs["group"] == pre_beamstop_group,
    )

    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "move_beamstop_in"
    )

    msgs = assert_expected_set(
        default_devices.aperture_scatterguard.selected_aperture,
        ApertureValue.SMALL,
        post_beamstop_group,
    )

    msgs = assert_expected_set(
        default_devices.cryojet.coarse, CryoInOut.IN, post_beamstop_group
    )
    msgs = assert_expected_set(
        default_devices.cryojet.fine, CryoInOut.IN, post_beamstop_group
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == post_beamstop_group,
    )


@pytest.mark.parametrize(
    "expected_raise, cryostream_selection, cryostream_selected",
    [
        [nullcontext(), CryoStreamSelection.CRYOJET, 1],
        [pytest.raises(CryoStreamError), CryoStreamSelection.HC1, 1],
        [pytest.raises(CryoStreamError), CryoStreamSelection.CRYOJET, 0],
    ],
)
def test_udc_default_state_checks_cryostream_selection(
    run_engine: RunEngine,
    default_devices,
    expected_raise,
    cryostream_selection: CryoStreamSelection,
    cryostream_selected: int,
):
    default_devices.scintillator._aperture_scatterguard().selected_aperture.get_value = MagicMock(
        return_value=ApertureValue.PARKED
    )
    set_mock_value(
        default_devices.cryostream_gantry.cryostream_selector, cryostream_selection
    )
    set_mock_value(
        default_devices.cryostream_gantry.cryostream_selected, cryostream_selected
    )

    with expected_raise:
        run_engine(move_to_udc_default_state(default_devices))


def test_udc_default_state_checks_that_pin_not_mounted(
    default_devices, sim_run_engine, beamline_parameters
):
    sim_run_engine.add_read_handler_for(
        default_devices.robot.gonio_pin_sensor, PinMounted.PIN_MOUNTED
    )
    with patch(
        "mx_bluesky.hyperion.experiment_plans.udc_default_state.get_beamline_parameters",
        return_value=beamline_parameters,
    ):
        with pytest.raises(UnexpectedSampleError):
            sim_run_engine.simulate_plan(move_to_udc_default_state(default_devices))


def test_default_state_closes_sample_shutter_before_open_hutch_shutter(
    sim_run_engine: RunEngineSimulator, default_devices: UDCDefaultDevices
):
    msgs = sim_run_engine.simulate_plan(move_to_udc_default_state(default_devices))
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is default_devices.sample_shutter
        and msg.args[0] == ZebraShutterState.CLOSE,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait"
        and msg.kwargs["group"] == msgs[0].kwargs["group"],
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj is default_devices.hutch_shutter
        and msg.args[0] == ShutterDemand.OPEN
        and msg.kwargs["group"] == "pre_beamstop_check",
    )


def test_default_state_hutch_shutter_open_is_skipped_if_commissioning_mode_enabled(
    sim_run_engine: RunEngineSimulator, default_devices: UDCDefaultDevices
):
    sim_run_engine.add_read_handler_for(default_devices.baton.commissioning, True)
    msgs = sim_run_engine.simulate_plan(move_to_udc_default_state(default_devices))
    open_shutter_msgs = [
        msg
        for msg in msgs
        if msg.command == "set"
        and msg.obj is default_devices.hutch_shutter
        and msg.args[0] == ShutterDemand.OPEN
    ]
    assert not open_shutter_msgs
