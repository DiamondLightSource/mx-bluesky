from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from bluesky.callbacks import CallbackBase
from bluesky.plan_stubs import null
from bluesky.run_engine import RunEngine
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from bluesky.utils import Msg, MsgGenerator
from dodal.devices.detector import DetectorParams
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import ZebraFastGridScanThreeD
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron, SynchrotronMode
from dodal.devices.zocalo.zocalo_results import (
    ZOCALO_STAGE_GROUP,
)
from event_model.documents import Event, RunStart
from numpy.testing import assert_equal
from ophyd_async.core import init_devices, set_mock_value

from mx_bluesky.common.device_setup_plans.detector.beamline_specific import (
    DiffractionEssentialDevices,
)
from mx_bluesky.common.device_setup_plans.detector.eiger import (
    create_eiger_beamline_specific,
)
from mx_bluesky.common.device_setup_plans.gridscan.beamline_specific import (
    BeamlineSpecificFGSFeatures,
)
from mx_bluesky.common.experiment_plans.inner_plans.do_fgs import (
    kickoff_and_complete_gridscan,
)
from mx_bluesky.common.external_interaction.callbacks.grid.grid_detect_and_scan.ispyb_callback import (
    GridscanPlane,
)
from mx_bluesky.common.parameters.components import DiffractionExperimentWithSample
from mx_bluesky.common.parameters.constants import (
    PlanNameConstants,
)
from mx_bluesky.common.parameters.gridscan import (
    GridScanParams,
    create_detector_params_for_grid_scan,
)


@pytest.fixture
def fgs_devices(run_engine, eiger):
    with init_devices(mock=True):
        synchrotron = Synchrotron()
        grid_scan_device = ZebraFastGridScanThreeD("zebra_fgs")

    return {
        "synchrotron": synchrotron,
        "grid_scan_device": grid_scan_device,
        "detector": eiger,
    }


@pytest.fixture
def fgs_composite(
    synchrotron: Synchrotron, eiger: EigerDetector, smargon: Smargon
) -> DiffractionEssentialDevices:
    return SimpleNamespace(  # type: ignore
        detector=eiger, synchrotron=synchrotron, gonio=smargon
    )


@pytest.fixture
def beamline_specific_fgs(
    minimal_diffraction_expt_with_sample: DiffractionExperimentWithSample,
    fgs_composite: DiffractionEssentialDevices,
    zebra_fast_grid_scan: ZebraFastGridScanThreeD,
) -> BeamlineSpecificFGSFeatures:
    beamline_specific_detector = create_eiger_beamline_specific(fgs_composite.detector)
    return BeamlineSpecificFGSFeatures(
        arm_detector_plan=beamline_specific_detector.arm_detector_plan,
        pre_arm_detector_plan=beamline_specific_detector.pre_arm_detector_plan,
        disarm_detector_plan=beamline_specific_detector.disarm_detector_plan,
        tidy_detector_plan=beamline_specific_detector.tidy_detector_plan,
        detector_hw_read_during_signals=beamline_specific_detector.detector_hw_read_during_signals,
        detector_zocalo_hw_read_signals=beamline_specific_detector.detector_zocalo_hw_read_signals,
        setup_trigger_plan=MagicMock(
            side_effect=lambda *args: (yield Msg("setup_trigger_plan"))  # type: ignore
        ),
        tidy_plan=MagicMock(side_effect=lambda *args: (yield Msg("tidy_plan"))),  # type: ignore
        set_flyscan_params_plan=MagicMock(
            lambda *args: (yield Msg("set_flyscan_params_plan"))  # type: ignore
        ),
        fgs_motors=zebra_fast_grid_scan,
        read_pre_flyscan_plan=MagicMock(
            lambda *args: (yield Msg("read_pre_flyscan_plan"))  # type: ignore
        ),
        read_during_collection_plan=MagicMock(
            lambda *args: (yield Msg("read_during_collection_plan"))  # type: ignore
        ),
    )


@pytest.fixture
def detector_params(
    minimal_diffraction_expt_with_sample: DiffractionExperimentWithSample,
) -> DetectorParams:
    return create_detector_params_for_grid_scan(minimal_diffraction_expt_with_sample)


@patch("mx_bluesky.common.experiment_plans.inner_plans.do_fgs.read_hardware_for_zocalo")
@patch(
    "mx_bluesky.common.experiment_plans.inner_plans.do_fgs.check_topup_and_wait_if_necessary"
)
def test_kickoff_and_complete_gridscan_correct_messages(
    mock_check_topup,
    mock_read_hardware,
    beamline_specific_fgs: BeamlineSpecificFGSFeatures,
    fgs_composite: DiffractionEssentialDevices,
    grid_scan_params_3d: GridScanParams,
    detector_params: DetectorParams,
    sim_run_engine: RunEngineSimulator,
):
    def null_plan() -> MsgGenerator:
        yield from null()

    msgs = sim_run_engine.simulate_plan(
        kickoff_and_complete_gridscan(
            beamline_specific_fgs,
            fgs_composite,
            grid_scan_params_3d,
            detector_params,
            plan_during_collection=null_plan,
        )
    )

    mock_check_topup.assert_called_once()
    mock_read_hardware.assert_called_once()

    msgs = assert_message_and_return_remaining(msgs, lambda msg: msg.command == "wait")

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "wait" and msg.kwargs["group"] == ZOCALO_STAGE_GROUP,
    )

    msgs = assert_message_and_return_remaining(
        msgs, lambda msg: msg.command == "kickoff"
    )

    msgs = assert_message_and_return_remaining(msgs, lambda msg: msg.command == "wait")

    msgs = assert_message_and_return_remaining(msgs, lambda msg: msg.command == "null")

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: (
            msg.command == "complete" and msg.obj.name == "zebra_fast_grid_scan"
        ),
    )

    msgs = assert_message_and_return_remaining(msgs, lambda msg: msg.command == "wait")


# This test should use the real Zocalo callbacks once https://github.com/DiamondLightSource/mx-bluesky/issues/215 is done
def test_kickoff_and_complete_gridscan_with_run_engine_correct_documents(
    run_engine: RunEngine,
    beamline_specific_fgs: BeamlineSpecificFGSFeatures,
    fgs_composite: DiffractionEssentialDevices,
    grid_scan_params_3d: GridScanParams,
    detector_params: DetectorParams,
):
    class TestCallback(CallbackBase):
        def start(self, doc: RunStart):
            self.subplan_name = doc.get("subplan_name")
            self.omega_to_scan_spec = doc.get("omega_to_scan_spec")

        def event(self, doc: Event):
            self.event_data = list(doc.get("data").keys())
            return doc

    test_callback = TestCallback()

    run_engine.subscribe(test_callback)
    synchrotron = fgs_composite.synchrotron
    set_mock_value(synchrotron.synchrotron_mode, SynchrotronMode.DEV)
    set_mock_value(beamline_specific_fgs.fgs_motors.status, 1)

    expected_scan_points = grid_scan_params_3d.scan_points
    with patch("mx_bluesky.common.experiment_plans.inner_plans.do_fgs.bps.complete"):
        run_engine(
            kickoff_and_complete_gridscan(
                beamline_specific_fgs,
                fgs_composite,
                grid_scan_params_3d,
                detector_params,
            )
        )

    assert test_callback.subplan_name == PlanNameConstants.DO_FGS
    assert test_callback.omega_to_scan_spec
    assert_equal(
        test_callback.omega_to_scan_spec[GridscanPlane.OMEGA_XY],
        expected_scan_points[0],
    )
    assert_equal(
        test_callback.omega_to_scan_spec[GridscanPlane.OMEGA_XZ],
        expected_scan_points[1],
    )
    assert len(test_callback.event_data) == 1
    assert test_callback.event_data[0] == "eiger_odin_file_writer_id"
