from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.collimation_table import CollimationTable
from dodal.devices.cryostream import CryoStream, CryoStreamGantry, CryoStreamSelection
from dodal.devices.cryostream import InOut as CryoInOut
from dodal.devices.fluorescence_detector_motion import FluorescenceDetector
from dodal.devices.fluorescence_detector_motion import InOut as FlouInOut
from dodal.devices.mx_phase1.beamstop import Beamstop, BeamstopPositions
from dodal.devices.scintillator import InOut, Scintillator
from dodal.testing import patch_all_motors
from ophyd_async.core import Signal, init_devices
from ophyd_async.epics.motor import Motor
from ophyd_async.testing import set_mock_value

from mx_bluesky.common.experiment_plans.inner_plans.udc_default_state import (
    UDCDefaultDevices,
    move_to_udc_default_state,
)


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
async def default_devices(aperture_scatterguard, cryostream_gantry):
    async with init_devices(mock=True):
        cryo = CryoStream("")
        fluo = FluorescenceDetector("")
        beamstop = Beamstop("", MagicMock())
        scintillator = Scintillator("", MagicMock(), MagicMock(), name="scin")
        collimation_table = CollimationTable("")

    with (
        patch_all_motors(scintillator),
        patch_all_motors(collimation_table),
        patch_all_motors(beamstop),
    ):
        yield UDCDefaultDevices(
            cryo,
            cryostream_gantry,
            fluo,
            beamstop,
            scintillator,
            aperture_scatterguard,
            collimation_table,
        )


async def test_given_cryostream_temp_is_too_high_then_exception_raised(
    RE: RunEngine,
    sim_run_engine: RunEngineSimulator,
    default_devices: UDCDefaultDevices,
):
    sim_run_engine.add_read_handler_for(
        default_devices.cryostream.temperature_k,
        default_devices.cryostream.MAX_TEMP_K + 10,
    )
    with pytest.raises(ValueError, match="temperature is too high"):
        sim_run_engine.simulate_plan(move_to_udc_default_state(default_devices))


async def test_given_cryostream_pressure_is_too_high_then_exception_raised(
    RE: RunEngine,
    sim_run_engine: RunEngineSimulator,
    default_devices: UDCDefaultDevices,
):
    sim_run_engine.add_read_handler_for(
        default_devices.cryostream.back_pressure_bar,
        default_devices.cryostream.MAX_PRESSURE_BAR + 10,
    )
    with pytest.raises(ValueError, match="pressure is too high"):
        sim_run_engine.simulate_plan(move_to_udc_default_state(default_devices))


async def test_scintillator_is_moved_out_before_aperture_scatterguard_moved_in(
    RE: RunEngine,
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


def test_udc_default_state_runs_in_real_RE(
    RE: RunEngine, default_devices: UDCDefaultDevices
):
    set_mock_value(default_devices.cryostream.temperature_k, 100)
    set_mock_value(default_devices.cryostream.back_pressure_bar, 0.01)
    default_devices.scintillator._aperture_scatterguard().selected_aperture.get_value = MagicMock(
        return_value=ApertureValue.PARKED
    )

    RE(move_to_udc_default_state(default_devices))


def test_udc_default_state_group_contains_expected_items_and_is_waited_on(
    RE: RunEngine,
    sim_run_engine: RunEngineSimulator,
    default_devices: UDCDefaultDevices,
):
    msgs = sim_run_engine.simulate_plan(move_to_udc_default_state(default_devices))

    expected_group = "udc_default"

    def assert_expected_set(signal: Signal | Motor, value):
        return assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "set"
            and msg.obj.name == signal.name
            and msg.args[0] == value
            and msg.kwargs["group"] == expected_group,
        )

    msgs = assert_expected_set(
        default_devices.fluorescence_det_motion.pos, FlouInOut.OUT
    )
    coll = default_devices.collimation_table
    for device in [
        coll.inboard_y,
        coll.outboard_y,
        coll.upstream_y,
        coll.upstream_x,
        coll.downstream_x,
    ]:
        msgs = assert_expected_set(device, 0)

    msgs = assert_expected_set(
        default_devices.beamstop.selected_pos, BeamstopPositions.DATA_COLLECTION
    )

    msgs = assert_expected_set(
        default_devices.aperture_scatterguard.selected_aperture, ApertureValue.SMALL
    )

    msgs = assert_expected_set(default_devices.cryostream.course, CryoInOut.IN)
    msgs = assert_expected_set(default_devices.cryostream.fine, CryoInOut.IN)

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait" and msg.kwargs["group"] == expected_group,
    )


@pytest.mark.parametrize(
    "expected_raise, cryostream_selection, cryostream_selected",
    [
        [nullcontext(), CryoStreamSelection.CRYOJET, 1],
        [pytest.raises(ValueError), CryoStreamSelection.HC1, 1],
        [pytest.raises(ValueError), CryoStreamSelection.CRYOJET, 0],
    ],
)
def test_udc_default_state_checks_cryostream_selection(
    RE: RunEngine,
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
        RE(move_to_udc_default_state(default_devices))
