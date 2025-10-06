import types
from functools import partial
from unittest.mock import MagicMock, call, patch

import bluesky.plan_stubs as bps
import numpy as np
import pytest
from bluesky.run_engine import RunEngine, RunEngineResult
from bluesky.simulators import assert_message_and_return_remaining
from bluesky.utils import FailedStatus, Msg
from dodal.beamlines import i03
from dodal.devices.detector.det_dim_constants import (
    EIGER_TYPE_EIGER2_X_16M,
)
from dodal.devices.fast_grid_scan import (
    ZebraFastGridScanThreeD,
    set_fast_grid_scan_params,
)
from dodal.devices.smargon import CombinedMove
from dodal.devices.synchrotron import SynchrotronMode
from dodal.devices.zocalo import ZocaloStartInfo
from numpy import isclose
from ophyd.sim import NullStatus
from ophyd.status import Status
from ophyd_async.testing import set_mock_value

from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    BeamlineSpecificFGSFeatures,
    FlyScanEssentialDevices,
    _fetch_xrc_results_from_zocalo,
    common_flyscan_xray_centre,
    kickoff_and_complete_gridscan,
    run_gridscan,
)
from mx_bluesky.common.experiment_plans.inner_plans.read_hardware import (
    read_hardware_plan,
)
from mx_bluesky.common.external_interaction.callbacks.common.logging_callback import (
    VerbosePlanExecutionLoggingCallback,
)
from mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback import (
    ZocaloCallback,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
    ispyb_activation_wrapper,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.nexus_callback import (
    GridscanNexusFileCallback,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_store import (
    IspybIds,
)
from mx_bluesky.common.parameters.constants import DocDescriptorNames
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
from mx_bluesky.common.utils.exceptions import (
    CrystalNotFoundException,
    WarningException,
)
from mx_bluesky.common.xrc_result import XRayCentreEventHandler, XRayCentreResult
from tests.conftest import (
    RunEngineSimulator,
    create_dummy_scan_spec,
)
from tests.unit_tests.hyperion.experiment_plans.conftest import mock_zocalo_trigger

from ....conftest import TestData
from ...conftest import (
    modified_store_grid_scan_mock,
    run_generic_ispyb_handler_setup,
)

ReWithSubs = tuple[RunEngine, tuple[GridscanNexusFileCallback, GridscanISPyBCallback]]


class CompleteException(Exception):
    # To avoid having to run through the entire plan during tests
    pass


def mock_plan():
    yield from bps.null()


@pytest.fixture
def RE_with_subs_snapshots_already_taken(RE_with_subs, TestEventData):
    RE, subscriptions = RE_with_subs
    ispyb_gridscan_callback = [
        sub for sub in subscriptions if isinstance(sub, GridscanISPyBCallback)
    ][0]
    ispyb_gridscan_callback.active = True
    ispyb_gridscan_callback.start(
        TestEventData.test_grid_detect_and_gridscan_start_document
    )  # type: ignore
    ispyb_gridscan_callback.start(TestEventData.test_gridscan_outer_start_document)  # type: ignore
    ispyb_gridscan_callback.descriptor(
        TestEventData.test_descriptor_document_oav_snapshot
    )
    ispyb_gridscan_callback.event(TestEventData.test_event_document_oav_snapshot_xy)
    ispyb_gridscan_callback.event(TestEventData.test_event_document_oav_snapshot_xz)
    return RE, subscriptions


@patch(
    "mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback.StoreInIspyb",
    modified_store_grid_scan_mock,
)
class TestFlyscanXrayCentrePlan:
    td: TestData = TestData()

    def test_eiger2_x_16_detector_specified(
        self,
        test_fgs_params: SpecifiedThreeDGridScan,
    ):
        assert (
            test_fgs_params.detector_params.detector_size_constants.det_type_string
            == EIGER_TYPE_EIGER2_X_16M
        )

    def test_when_run_gridscan_called_then_generator_returned(
        self,
    ):
        plan = run_gridscan(MagicMock(), MagicMock(), MagicMock())
        assert isinstance(plan, types.GeneratorType)

    def test_when_run_gridscan_called_ispyb_deposition_made_and_records_errors(
        self,
        RE: RunEngine,
        fake_fgs_composite: FlyScanEssentialDevices,
        test_fgs_params: SpecifiedThreeDGridScan,
        beamline_specific: BeamlineSpecificFGSFeatures,
    ):
        ispyb_callback = GridscanISPyBCallback(param_type=SpecifiedThreeDGridScan)
        RE.subscribe(ispyb_callback)

        error = None
        with patch.object(fake_fgs_composite.smargon.omega, "set") as mock_set:
            error = AssertionError("Test Exception")
            mock_set.return_value = FailedStatus(error)
            with pytest.raises(FailedStatus) as exc:
                RE(
                    ispyb_activation_wrapper(
                        common_flyscan_xray_centre(
                            fake_fgs_composite, test_fgs_params, beamline_specific
                        ),
                        test_fgs_params,
                    ),
                )

        assert exc.value.args[0] is error
        ispyb_callback.ispyb.end_deposition.assert_called_once_with(  # type: ignore
            IspybIds(data_collection_group_id=0, data_collection_ids=(0, 0)),
            "fail",
            "Test Exception",
        )

    @patch("bluesky.plan_stubs.abs_set", autospec=True)
    def test_results_passed_to_move_motors(
        self,
        bps_abs_set: MagicMock,
        test_fgs_params: SpecifiedThreeDGridScan,
        fake_fgs_composite: FlyScanEssentialDevices,
        RE: RunEngine,
    ):
        from mx_bluesky.common.device_setup_plans.manipulate_sample import move_x_y_z

        motor_position = test_fgs_params.FGS_params.grid_position_to_motor_position(
            np.array([1, 2, 3])
        )
        RE(move_x_y_z(fake_fgs_composite.smargon, *motor_position))
        bps_abs_set.assert_called_with(
            fake_fgs_composite.smargon,
            CombinedMove(x=motor_position[0], y=motor_position[1], z=motor_position[2]),
            group="move_x_y_z",
        )

    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.run_gridscan",
    )
    @patch(
        "mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback.ZocaloTrigger",
    )
    def test_individual_plans_triggered_once_and_only_once_in_composite_run(
        self,
        zoc_trigger: MagicMock,
        run_gridscan: MagicMock,
        RE_with_subs: ReWithSubs,
        fake_fgs_composite: FlyScanEssentialDevices,
        test_fgs_params: SpecifiedThreeDGridScan,
        beamline_specific: BeamlineSpecificFGSFeatures,
    ):
        RE, _ = RE_with_subs

        def wrapped_gridscan_and_move():
            yield from common_flyscan_xray_centre(
                fake_fgs_composite,
                test_fgs_params,
                beamline_specific,
            )

        RE(wrapped_gridscan_and_move())
        run_gridscan.assert_called_once()
        beamline_specific.setup_trigger_plan.assert_called_once()  # type: ignore
        beamline_specific.tidy_plan.assert_called_once()  # type: ignore

    @patch(
        "mx_bluesky.common.experiment_plans.inner_plans.do_fgs.check_topup_and_wait_if_necessary",
    )
    def test_waits_for_motion_program(
        self,
        check_topup_and_wait,
        RE: RunEngine,
        test_fgs_params: SpecifiedThreeDGridScan,
        fake_fgs_composite: FlyScanEssentialDevices,
        done_status: Status,
    ):
        fake_fgs_composite.eiger.unstage = MagicMock(return_value=done_status)
        fgs = i03.zebra_fast_grid_scan(connect_immediately=True, mock=True)
        fgs.KICKOFF_TIMEOUT = 0.1
        fgs.complete = MagicMock(return_value=done_status)
        set_mock_value(fgs.motion_program.running, 1)

        def test_plan():
            yield from kickoff_and_complete_gridscan(
                fgs,
                fake_fgs_composite.eiger,
                fake_fgs_composite.synchrotron,
                [
                    test_fgs_params.scan_points_first_grid,
                    test_fgs_params.scan_points_second_grid,
                ],
            )

        with pytest.raises(FailedStatus):
            RE(test_plan())
        fgs.KICKOFF_TIMEOUT = 1
        set_mock_value(fgs.motion_program.running, 0)
        set_mock_value(fgs.status, 1)
        res = RE(test_plan())

        assert isinstance(res, RunEngineResult)
        assert res.exit_status == "success"

    def test_if_timeout_fails_then_sample_exception_raised(
        self,
        RE: RunEngine,
        fake_fgs_composite: FlyScanEssentialDevices,
        beamline_specific: BeamlineSpecificFGSFeatures,
        test_fgs_params: SpecifiedThreeDGridScan,
    ):
        beamline_specific.set_flyscan_params_plan = partial(
            set_fast_grid_scan_params,
            beamline_specific.fgs_motors,
            test_fgs_params.FGS_params,
        )

        set_mock_value(beamline_specific.fgs_motors.device_scan_invalid, 1.0)  # type: ignore

        with pytest.raises(WarningException):
            RE(run_gridscan(fake_fgs_composite, test_fgs_params, beamline_specific))

    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.bps.abs_set",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.bps.kickoff",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.bps.complete",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.bps.mv",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.external_interaction.nexus.write_nexus.NexusWriter",
        autospec=True,
        spec_set=True,
    )
    @patch(
        "mx_bluesky.common.experiment_plans.inner_plans.do_fgs.check_topup_and_wait_if_necessary",
        autospec=True,
    )
    def test_when_grid_scan_ran_then_eiger_disarmed_before_zocalo_end(
        self,
        mock_check_topup,
        nexuswriter,
        mock_mv,
        mock_complete,
        mock_kickoff,
        mock_abs_set,
        fake_fgs_composite: FlyScanEssentialDevices,
        test_fgs_params: SpecifiedThreeDGridScan,
        RE_with_subs_snapshots_already_taken: ReWithSubs,
        beamline_specific: BeamlineSpecificFGSFeatures,
    ):
        test_fgs_params.x_steps = 9
        test_fgs_params.y_steps = 10
        test_fgs_params.z_steps = 12
        RE, (nexus_cb, ispyb_cb) = RE_with_subs_snapshots_already_taken
        # Put both mocks in a parent to easily capture order
        mock_parent = MagicMock()
        fake_fgs_composite.eiger.disarm_detector = mock_parent.disarm
        assert isinstance(ispyb_cb.emit_cb, ZocaloCallback)
        ispyb_cb.emit_cb.zocalo_interactor.run_end = mock_parent.run_end

        fake_fgs_composite.eiger.filewriters_finished = NullStatus()  # type: ignore
        fake_fgs_composite.eiger.odin.check_and_wait_for_odin_state = MagicMock(
            return_value=True
        )
        fake_fgs_composite.eiger.odin.file_writer.num_captured.sim_put(1200)  # type: ignore
        fake_fgs_composite.eiger.stage = MagicMock(
            return_value=Status(None, None, 0, True, True)
        )

        with patch(
            "mx_bluesky.common.external_interaction.callbacks.xray_centre.nexus_callback.NexusWriter.create_nexus_file",
            autospec=True,
        ):
            [RE.subscribe(cb) for cb in (nexus_cb, ispyb_cb)]
            RE(
                ispyb_activation_wrapper(
                    common_flyscan_xray_centre(
                        fake_fgs_composite, test_fgs_params, beamline_specific
                    ),
                    test_fgs_params,
                )
            )

        mock_parent.assert_has_calls(
            [call.disarm(), call.run_end(100), call.run_end(200)]
        )

    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.bps.wait",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.bps.complete",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.bps.kickoff",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.experiment_plans.inner_plans.do_fgs.check_topup_and_wait_if_necessary",
        autospec=True,
    )
    def test_fgs_arms_eiger_without_grid_detect(
        self,
        mock_topup,
        mock_kickoff,
        mock_complete,
        mock_wait,
        fake_fgs_composite: FlyScanEssentialDevices,
        test_fgs_params: SpecifiedThreeDGridScan,
        RE: RunEngine,
        done_status: Status,
        beamline_specific: BeamlineSpecificFGSFeatures,
    ):
        fake_fgs_composite.eiger.unstage = MagicMock(return_value=done_status)
        RE(run_gridscan(fake_fgs_composite, test_fgs_params, beamline_specific))
        fake_fgs_composite.eiger.stage.assert_called_once()  # type: ignore
        fake_fgs_composite.eiger.unstage.assert_called_once()

    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.bps.kickoff",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.bps.wait",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.bps.complete",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.experiment_plans.inner_plans.do_fgs.check_topup_and_wait_if_necessary",
        autospec=True,
    )
    def test_when_grid_scan_fails_with_exception_then_detector_disarmed_and_correct_exception_returned(
        self,
        mock_topup,
        mock_complete,
        mock_wait,
        mock_kickoff,
        fake_fgs_composite: FlyScanEssentialDevices,
        test_fgs_params: SpecifiedThreeDGridScan,
        RE: RunEngine,
        beamline_specific: BeamlineSpecificFGSFeatures,
    ):
        beamline_specific.read_pre_flyscan_plan = partial(
            read_hardware_plan,
            [],
            DocDescriptorNames.HARDWARE_READ_DURING,
        )

        mock_complete.side_effect = CompleteException()

        fake_fgs_composite.eiger.stage = MagicMock(
            return_value=Status(None, None, 0, True, True)
        )

        fake_fgs_composite.eiger.filewriters_finished = NullStatus()

        fake_fgs_composite.eiger.odin.check_and_wait_for_odin_state = MagicMock()

        fake_fgs_composite.eiger.disarm_detector = MagicMock()
        fake_fgs_composite.eiger.disable_roi_mode = MagicMock()

        with pytest.raises(CompleteException):
            RE(run_gridscan(fake_fgs_composite, test_fgs_params, beamline_specific))

        fake_fgs_composite.eiger.disable_roi_mode.assert_called()
        fake_fgs_composite.eiger.disarm_detector.assert_called()

    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.bps.kickoff",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.bps.complete",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.experiment_plans.inner_plans.do_fgs.check_topup_and_wait_if_necessary",
        autospec=True,
    )
    def test_kickoff_and_complete_gridscan_triggers_zocalo(
        self,
        mock_topup,
        mock_complete: MagicMock,
        mock_kickoff: MagicMock,
        RE_with_subs_snapshots_already_taken,
        fake_fgs_composite: FlyScanEssentialDevices,
        dummy_rotation_data_collection_group_info,
        zebra_fast_grid_scan: ZebraFastGridScanThreeD,
    ):
        id_1, id_2 = 100, 200

        RE, subs = RE_with_subs_snapshots_already_taken
        _, ispyb_cb = subs
        ispyb_cb.active = True
        ispyb_cb.ispyb = MagicMock()
        ispyb_cb.params = MagicMock()
        ispyb_cb.ispyb_ids.data_collection_ids = (id_1, id_2)
        ispyb_cb.data_collection_group_info = dummy_rotation_data_collection_group_info
        assert isinstance(ispyb_cb.emit_cb, ZocaloCallback)

        mock_zocalo_trigger = ispyb_cb.emit_cb.zocalo_interactor

        fake_fgs_composite.eiger.unstage = MagicMock()
        fake_fgs_composite.eiger.odin.file_writer.id.sim_put("test/filename")  # type: ignore

        x_steps, y_steps, z_steps = 10, 20, 30

        RE.subscribe(ispyb_cb)

        RE(
            kickoff_and_complete_gridscan(
                zebra_fast_grid_scan,
                fake_fgs_composite.eiger,
                fake_fgs_composite.synchrotron,
                scan_points=create_dummy_scan_spec(),
            )
        )

        expected_start_infos = [
            ZocaloStartInfo(id_1, "test/filename", 0, x_steps * y_steps, 0),
            ZocaloStartInfo(
                id_2, "test/filename", x_steps * y_steps, x_steps * z_steps, 1
            ),
        ]

        expected_start_calls = [
            call(expected_start_infos[0]),
            call(expected_start_infos[1]),
        ]

        assert mock_zocalo_trigger.run_start.call_count == 2  # type: ignore
        assert mock_zocalo_trigger.run_start.mock_calls == expected_start_calls  # type: ignore

        assert mock_zocalo_trigger.run_end.call_count == 2  # type: ignore
        assert mock_zocalo_trigger.run_end.mock_calls == [call(id_1), call(id_2)]  # type: ignore

    @patch(
        "mx_bluesky.common.experiment_plans.inner_plans.do_fgs.check_topup_and_wait_if_necessary",
        new=MagicMock(side_effect=lambda *_, **__: iter([Msg("check_topup")])),
    )
    def test_read_hardware_during_collection_occurs_after_eiger_arm(
        self,
        fake_fgs_composite: FlyScanEssentialDevices,
        test_fgs_params: SpecifiedThreeDGridScan,
        sim_run_engine: RunEngineSimulator,
        beamline_specific: BeamlineSpecificFGSFeatures,
    ):
        beamline_specific.read_during_collection_plan = partial(
            read_hardware_plan,
            [fake_fgs_composite.eiger.bit_depth],  # type: ignore # see https://github.com/bluesky/bluesky/issues/1809
            DocDescriptorNames.HARDWARE_READ_DURING,
        )
        sim_run_engine.add_handler(
            "read",
            lambda msg: {"values": {"value": SynchrotronMode.USER}},
            "synchrotron-synchrotron_mode",
        )
        msgs = sim_run_engine.simulate_plan(
            run_gridscan(fake_fgs_composite, test_fgs_params, beamline_specific)
        )
        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "stage" and msg.obj.name == "eiger"
        )
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "kickoff"
            and msg.obj == beamline_specific.fgs_motors,
        )
        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "create"
        )
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "read" and msg.obj.name == "eiger_bit_depth",
        )
        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "save"
        )

    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.run_gridscan",
        autospec=True,
    )
    def test_when_gridscan_succeeds_and_results_fetched_ispyb_comment_appended_to(
        self,
        run_gridscan: MagicMock,
        RE_with_subs: ReWithSubs,
        test_fgs_params: SpecifiedThreeDGridScan,
        fake_fgs_composite: FlyScanEssentialDevices,
        beamline_specific: BeamlineSpecificFGSFeatures,
    ):
        RE, (nexus_cb, ispyb_cb) = RE_with_subs

        def _wrapped_gridscan_and_move():
            run_generic_ispyb_handler_setup(ispyb_cb, test_fgs_params)
            yield from common_flyscan_xray_centre(
                fake_fgs_composite,
                test_fgs_params,
                beamline_specific,
            )

        RE.subscribe(VerbosePlanExecutionLoggingCallback())
        beamline_specific.get_xrc_results_from_zocalo = True
        RE(ispyb_activation_wrapper(_wrapped_gridscan_and_move(), test_fgs_params))
        app_to_comment: MagicMock = ispyb_cb.ispyb.append_to_comment  # type:ignore
        app_to_comment.assert_called()
        append_aperture_call = app_to_comment.call_args_list[0].args[1]
        assert "Aperture:" in append_aperture_call

    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.run_gridscan",
        autospec=True,
    )
    async def test_results_adjusted_and_event_raised(
        self,
        run_gridscan: MagicMock,
        fake_fgs_composite: FlyScanEssentialDevices,
        test_fgs_params: SpecifiedThreeDGridScan,
        beamline_specific: BeamlineSpecificFGSFeatures,
        RE_with_subs: ReWithSubs,
    ):
        RE, _ = RE_with_subs
        beamline_specific.get_xrc_results_from_zocalo = True
        x_ray_centre_event_handler = XRayCentreEventHandler()
        RE.subscribe(x_ray_centre_event_handler)
        mock_zocalo_trigger(fake_fgs_composite.zocalo, TestData.test_result_large)

        def plan():
            yield from _fetch_xrc_results_from_zocalo(
                fake_fgs_composite.zocalo, test_fgs_params
            )

        RE(plan())

        actual = x_ray_centre_event_handler.xray_centre_results
        expected = XRayCentreResult(
            centre_of_mass_mm=np.array([0.05, 0.15, 0.25]),
            bounding_box_mm=(
                np.array([0.15, 0.15, 0.15]),
                np.array([0.75, 0.75, 0.65]),
            ),
            max_count=105062,
            total_count=2387574,
            sample_id=12345,
        )
        assert actual and len(actual) == 1
        assert all(isclose(actual[0].centre_of_mass_mm, expected.centre_of_mass_mm))
        assert all(isclose(actual[0].bounding_box_mm[0], expected.bounding_box_mm[0]))
        assert all(isclose(actual[0].bounding_box_mm[1], expected.bounding_box_mm[1]))

    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.kickoff_and_complete_gridscan",
        MagicMock(),
    )
    def test_run_gridscan_and_fetch_results_discards_results_below_threshold(
        self,
        fake_fgs_composite: FlyScanEssentialDevices,
        test_fgs_params: SpecifiedThreeDGridScan,
        beamline_specific: BeamlineSpecificFGSFeatures,
        RE: RunEngine,
    ):
        beamline_specific.get_xrc_results_from_zocalo = True
        callback = XRayCentreEventHandler()
        RE.subscribe(callback)

        mock_zocalo_trigger(
            fake_fgs_composite.zocalo,
            TestData.test_result_medium
            + TestData.test_result_below_threshold
            + TestData.test_result_small,
        )
        RE(_fetch_xrc_results_from_zocalo(fake_fgs_composite.zocalo, test_fgs_params))

        assert callback.xray_centre_results and len(callback.xray_centre_results) == 2
        assert [r.max_count for r in callback.xray_centre_results] == [50000, 1000]

    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.run_gridscan",
        autospec=True,
    )
    def test_when_gridscan_finds_no_xtal_exception_is_raised(
        self,
        run_gridscan: MagicMock,
        RE_with_subs: ReWithSubs,
        test_fgs_params: SpecifiedThreeDGridScan,
        fake_fgs_composite: FlyScanEssentialDevices,
        beamline_specific: BeamlineSpecificFGSFeatures,
    ):
        RE, (nexus_cb, ispyb_cb) = RE_with_subs
        beamline_specific.get_xrc_results_from_zocalo = True

        def wrapped_gridscan_and_move():
            run_generic_ispyb_handler_setup(ispyb_cb, test_fgs_params)
            yield from common_flyscan_xray_centre(
                fake_fgs_composite,
                test_fgs_params,
                beamline_specific,
            )

        mock_zocalo_trigger(fake_fgs_composite.zocalo, [])
        with pytest.raises(CrystalNotFoundException):
            RE(ispyb_activation_wrapper(wrapped_gridscan_and_move(), test_fgs_params))

    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.run_gridscan",
        MagicMock(),
    )
    def test_dummy_result_returned_when_gridscan_finds_no_xtal_and_commissioning_mode_enabled(
        self,
        RE: RunEngine,
        test_fgs_params: SpecifiedThreeDGridScan,
        fake_fgs_composite: FlyScanEssentialDevices,
        beamline_specific: BeamlineSpecificFGSFeatures,
        baton_in_commissioning_mode,
    ):
        xrc_event_handler = XRayCentreEventHandler()
        RE.subscribe(xrc_event_handler)
        beamline_specific.get_xrc_results_from_zocalo = True

        mock_zocalo_trigger(fake_fgs_composite.zocalo, [])
        RE(
            common_flyscan_xray_centre(
                fake_fgs_composite,
                test_fgs_params,
                beamline_specific,
            )
        )

        results = xrc_event_handler.xray_centre_results or []
        assert len(results) == 1
        result = results[0]
        assert result.sample_id == test_fgs_params.sample_id
        assert result.max_count == 10000
        assert result.total_count == 100000
        assert all(np.isclose(result.bounding_box_mm[0], [1.95, 0.95, 0.45]))
        assert all(np.isclose(result.bounding_box_mm[1], [2.05, 1.05, 0.55]))
        assert all(np.isclose(result.centre_of_mass_mm, [2.0, 1.0, 0.5]))
