from __future__ import annotations

from unittest.mock import DEFAULT, patch

import bluesky.plan_stubs as bps
import pydantic
import pytest
from bluesky import preprocessors as bpp
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.beamlines import i03
from dodal.beamlines.i03 import eiger
from dodal.devices.aperturescatterguard import (
    AperturePosition,
    ApertureScatterguard,
    ApertureValue,
)
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.dcm import DCM
from dodal.devices.eiger import EigerDetector
from dodal.devices.flux import Flux
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron, SynchrotronMode
from dodal.devices.undulator import Undulator
from ophyd_async.testing import set_mock_value

from mx_bluesky.common.external_interaction.callbacks.common.plan_reactive_callback import (
    PlanReactiveCallback,
)
from mx_bluesky.common.parameters.constants import PlanNameConstants
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
from mx_bluesky.common.plans.read_hardware_plan import (
    ReadHardwareTime,
    read_hardware_for_zocalo,
    read_hardware_plan,
)
from mx_bluesky.common.utils.log import ISPYB_ZOCALO_CALLBACK_LOGGER

from ...conftest import assert_event


@pytest.fixture
def ispyb_plan(test_fgs_params: SpecifiedThreeDGridScan):
    @bpp.set_run_key_decorator(PlanNameConstants.GRIDSCAN_OUTER)
    @bpp.run_decorator(  # attach experiment metadata to the start document
        md={
            "subplan_name": PlanNameConstants.GRIDSCAN_OUTER,
            "mx_bluesky_parameters": test_fgs_params.model_dump_json(),
        }
    )
    def standalone_read_hardware_for_ispyb(*args):
        yield from read_hardware_plan([*args], ReadHardwareTime.PRE_COLLECTION)
        yield from read_hardware_plan([*args], ReadHardwareTime.DURING_COLLECTION)

    return standalone_read_hardware_for_ispyb


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class FakeComposite:
    aperture_scatterguard: ApertureScatterguard
    attenuator: BinaryFilterAttenuator
    dcm: DCM
    flux: Flux
    s4_slit_gaps: S4SlitGaps
    undulator: Undulator
    synchrotron: Synchrotron
    robot: BartRobot
    smargon: Smargon
    eiger: EigerDetector


@pytest.fixture
async def fake_composite(
    RE: RunEngine,
    attenuator,
    aperture_scatterguard,
    dcm,
    synchrotron,
    robot,
    smargon,
) -> FakeComposite:
    fake_composite = FakeComposite(
        aperture_scatterguard=aperture_scatterguard,
        attenuator=attenuator,
        dcm=dcm,
        flux=i03.flux(fake_with_ophyd_sim=True),
        s4_slit_gaps=i03.s4_slit_gaps(fake_with_ophyd_sim=True),
        undulator=i03.undulator(fake_with_ophyd_sim=True),
        synchrotron=synchrotron,
        robot=robot,
        smargon=smargon,
        eiger=eiger(fake_with_ophyd_sim=True),
    )
    return fake_composite


@pytest.fixture
def fake_eiger() -> EigerDetector:
    return eiger(fake_with_ophyd_sim=True)


def test_read_hardware_for_zocalo_in_RE(fake_eiger, RE: RunEngine):
    def open_run_and_read_hardware():
        yield from bps.open_run()
        yield from read_hardware_for_zocalo(fake_eiger)

    RE(open_run_and_read_hardware())


def test_read_hardware_correct_messages(fake_eiger, sim_run_engine: RunEngineSimulator):
    msgs = sim_run_engine.simulate_plan(read_hardware_for_zocalo(fake_eiger))
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "create"
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "read"
        and msg.obj.name == "eiger_odin_file_writer_id",
    )
    msgs = assert_message_and_return_remaining(msgs, lambda msg: msg.command == "save")


def test_read_hardware_for_ispyb_updates_from_ophyd_devices(
    fake_composite: FakeComposite,
    test_fgs_params: SpecifiedThreeDGridScan,
    RE: RunEngine,
    ispyb_plan,
):
    undulator_test_value = 1.234

    set_mock_value(fake_composite.undulator.current_gap, undulator_test_value)

    synchrotron_test_value = SynchrotronMode.USER
    set_mock_value(fake_composite.synchrotron.synchrotron_mode, synchrotron_test_value)

    transmission_test_value = 0.01
    set_mock_value(
        fake_composite.attenuator.actual_transmission, transmission_test_value
    )

    current_energy_kev_test_value = 12.05
    set_mock_value(
        fake_composite.dcm.energy_in_kev.user_readback,
        current_energy_kev_test_value,
    )

    xgap_test_value = 0.1234
    ygap_test_value = 0.2345
    ap_sg_test_value = AperturePosition(
        aperture_x=10,
        aperture_y=11,
        aperture_z=2,
        scatterguard_x=13,
        scatterguard_y=14,
        radius=20,
    )
    set_mock_value(fake_composite.s4_slit_gaps.xgap.user_readback, xgap_test_value)
    set_mock_value(fake_composite.s4_slit_gaps.ygap.user_readback, ygap_test_value)
    flux_test_value = 10.0
    set_mock_value(fake_composite.flux.flux_reading, flux_test_value)

    RE(
        bps.abs_set(
            fake_composite.aperture_scatterguard,
            ApertureValue.SMALL,
        )
    )

    test_ispyb_callback = PlanReactiveCallback(ISPYB_ZOCALO_CALLBACK_LOGGER)
    test_ispyb_callback.active = True

    with patch.multiple(
        test_ispyb_callback,
        activity_gated_start=DEFAULT,
        activity_gated_event=DEFAULT,
    ):
        RE.subscribe(test_ispyb_callback)

        RE(
            ispyb_plan(
                fake_composite.undulator.current_gap,
                fake_composite.synchrotron.synchrotron_mode,
                fake_composite.s4_slit_gaps.xgap,
                fake_composite.s4_slit_gaps.ygap,
                fake_composite.flux.flux_reading,
                fake_composite.dcm.energy_in_kev,
                fake_composite.aperture_scatterguard,
                fake_composite.smargon,
                fake_composite.eiger.bit_depth,
                fake_composite.attenuator.actual_transmission,
            )
        )
        # fmt: off
        assert_event(
            test_ispyb_callback.activity_gated_start.mock_calls[0],  # pyright: ignore
            {
                "plan_name": "standalone_read_hardware_for_ispyb",
                "subplan_name": "run_gridscan_move_and_tidy",
            },
        )
        assert_event(
            test_ispyb_callback.activity_gated_event.mock_calls[0],  # pyright: ignore
            {
                "undulator-current_gap": undulator_test_value,
                "synchrotron-synchrotron_mode": synchrotron_test_value.value,
                "s4_slit_gaps-xgap": xgap_test_value,
                "s4_slit_gaps-ygap": ygap_test_value,
            },
        )
        assert_event(
            test_ispyb_callback.activity_gated_event.mock_calls[1],  # pyright: ignore
            {
                "aperture_scatterguard-selected_aperture": ApertureValue.SMALL,
                "aperture_scatterguard-aperture-x": ap_sg_test_value.aperture_x,
                "aperture_scatterguard-aperture-y": ap_sg_test_value.aperture_y,
                "aperture_scatterguard-aperture-z": ap_sg_test_value.aperture_z,
                "aperture_scatterguard-scatterguard-x": ap_sg_test_value.scatterguard_x,
                "aperture_scatterguard-scatterguard-y": ap_sg_test_value.scatterguard_y,
                "aperture_scatterguard-radius": ap_sg_test_value.radius,
                "attenuator-actual_transmission": transmission_test_value,
                "flux-flux_reading": flux_test_value,
                "dcm-energy_in_kev": current_energy_kev_test_value,
            },
        )
        # fmt: on
