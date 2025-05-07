from unittest.mock import ANY, MagicMock, call, patch

import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import assert_message_and_return_remaining

from mx_bluesky.common.parameters.constants import (
    PlanNameConstants,
)
from mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan import (
    hyperion_grid_detect_then_xray_centre,
)
from mx_bluesky.hyperion.parameters.device_composites import (
    HyperionGridDetectThenXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import (
    GridScanWithEdgeDetect,
)
from tests.conftest import (
    RunEngineSimulator,
)
from tests.unit_tests.common.plans.test_common_flyscan_xray_centre_plan import (
    CompleteException,
)

from ....conftest import TEST_RESULT_LARGE, simulate_xrc_result


class TestHyperionGridDetectThenXrayCentrePlan:
    @patch(
        "mx_bluesky.common.preprocessors.preprocessors.check_and_pause_feedback",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.preprocessors.preprocessors.unpause_xbpm_feedback_and_set_transmission_to_1",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.run_gridscan",
    )
    def test_flyscan_xray_centre_unpauses_xbpm_feedback_on_exception(
        self,
        fake_run_gridscan: MagicMock,
        mock_unpause_and_set_transmission: MagicMock,
        mock_check_and_pause: MagicMock,
        grid_detect_devices: HyperionGridDetectThenXRayCentreComposite,
        test_full_grid_scan_params: GridScanWithEdgeDetect,
        test_config_files,
        RE: RunEngine,
    ):
        fake_run_gridscan.side_effect = Exception
        with pytest.raises(Exception):  # noqa: B017
            RE(
                hyperion_grid_detect_then_xray_centre(
                    grid_detect_devices,
                    test_full_grid_scan_params,
                    test_config_files["oav_config_json"],
                )
            )

        # Called once on exception and once on close_run
        mock_unpause_and_set_transmission.assert_has_calls([call(ANY, ANY)])

    @patch(
        "mx_bluesky.hyperion.experiment_plans.hyperion_flyscan_xray_centre_plan.bps.wait"
    )
    @patch(
        "mx_bluesky.common.experiment_plans.inner_plans.do_fgs.check_topup_and_wait_if_necessary",
    )
    def test_flyscan_xray_centre_pauses_and_unpauses_xbpm_feedback_in_correct_order(
        self,
        mock_check_topup,
        mock_wait,
        sim_run_engine: RunEngineSimulator,
        test_full_grid_scan_params: GridScanWithEdgeDetect,
        grid_detect_devices: HyperionGridDetectThenXRayCentreComposite,
        test_config_files,
    ):
        simulate_xrc_result(
            sim_run_engine, grid_detect_devices.zocalo, TEST_RESULT_LARGE
        )

        msgs = sim_run_engine.simulate_plan(
            hyperion_grid_detect_then_xray_centre(
                grid_detect_devices,
                test_full_grid_scan_params,
                test_config_files["oav_config_json"],
            )
        )

        # Assert order: pause -> open run -> close run -> unpause (set attenuator)
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "trigger" and msg.obj.name == "xbpm_feedback",
        )
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "open_run"
            and msg.run == PlanNameConstants.GRIDSCAN_OUTER,
        )

        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "close_run"
            and msg.run == PlanNameConstants.GRIDSCAN_OUTER,
        )

        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "set"
            and msg.obj.name == "attenuator"
            and msg.args == (1.0,),
        )

    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.run_gridscan",
    )
    @patch(
        "dodal.plans.preprocessors.verify_undulator_gap.verify_undulator_gap",
    )
    def test_hyperion_grid_detect_then_xray_centre_does_undulator_check_before_collection(
        self,
        mock_verify_gap: MagicMock,
        mock_plan: MagicMock,
        RE: RunEngine,
        test_full_grid_scan_params: GridScanWithEdgeDetect,
        grid_detect_devices: HyperionGridDetectThenXRayCentreComposite,
        test_config_files,
    ):
        mock_plan.side_effect = CompleteException
        with pytest.raises(CompleteException):
            RE(
                hyperion_grid_detect_then_xray_centre(
                    grid_detect_devices,
                    test_full_grid_scan_params,
                    test_config_files["oav_config_json"],
                )
            )

        mock_verify_gap.assert_called_once()
