from __future__ import annotations

import bluesky.plan_stubs as bps
import pydantic
import pytest
from bluesky import preprocessors as bpp
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.beamlines import i03
from dodal.beamlines.i03 import eiger
from dodal.devices.aperturescatterguard import (
    ApertureScatterguard,
)
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.eiger import EigerDetector
from dodal.devices.flux import Flux
from dodal.devices.i03.dcm import DCM
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.undulator import Undulator

from mx_bluesky.common.parameters.constants import DocDescriptorNames, PlanNameConstants
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
from mx_bluesky.common.plans.read_hardware import (
    read_hardware_for_zocalo,
    read_hardware_plan,
)


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
        yield from read_hardware_plan([*args], DocDescriptorNames.HARDWARE_READ_PRE)
        yield from read_hardware_plan([*args], DocDescriptorNames.HARDWARE_READ_DURING)

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
        flux=i03.flux(connect_immediately=True, mock=True),
        s4_slit_gaps=i03.s4_slit_gaps(connect_immediately=True, mock=True),
        undulator=i03.undulator(connect_immediately=True, mock=True),
        synchrotron=synchrotron,
        robot=robot,
        smargon=smargon,
        eiger=eiger(connect_immediately=True, mock=True),
    )
    return fake_composite


def test_read_hardware_for_zocalo_in_RE(fake_composite: FakeComposite, RE: RunEngine):
    def open_run_and_read_hardware():
        yield from bps.open_run()
        yield from read_hardware_for_zocalo(fake_composite.eiger)

    RE(open_run_and_read_hardware())


def test_read_hardware_correct_messages(
    fake_composite: FakeComposite, sim_run_engine: RunEngineSimulator
):
    msgs = sim_run_engine.simulate_plan(read_hardware_for_zocalo(fake_composite.eiger))
    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "create"
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "read"
        and msg.obj.name == "eiger_odin_file_writer_id",
    )
    msgs = assert_message_and_return_remaining(msgs, lambda msg: msg.command == "save")
