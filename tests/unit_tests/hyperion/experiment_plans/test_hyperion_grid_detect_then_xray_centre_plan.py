from collections.abc import Generator
from typing import cast
from unittest.mock import ANY, MagicMock, call, patch

import pytest
from bluesky.run_engine import RunEngine
from dodal.devices.oav.pin_image_recognition import PinTipDetection

from mx_bluesky.hyperion.experiment_plans.hyperion_grid_detect_then_xray_centre_plan import (
    hyperion_grid_detect_then_xray_centre,
)
from mx_bluesky.hyperion.parameters.device_composites import (
    HyperionGridDetectThenXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import (
    GridScanWithEdgeDetect,
    HyperionSpecifiedThreeDGridScan,
)
from tests.unit_tests.common.experiment_plans.test_common_flyscan_xray_centre_plan import (
    CompleteException,
)


class TestHyperionGridDetectThenXrayCentrePlan:
    def test_full_hyperion_grid_scan(
        self,
        hyperion_fgs_params: HyperionSpecifiedThreeDGridScan,
        test_config_files: dict[str, str],
    ):
        devices = MagicMock()
        plan = hyperion_grid_detect_then_xray_centre(
            devices,
            cast(GridScanWithEdgeDetect, hyperion_fgs_params),
            test_config_files["oav_config_json"],
        )
        assert isinstance(plan, Generator)

    @patch(
        "mx_bluesky.common.preprocessors.preprocessors.check_and_pause_feedback",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.preprocessors.preprocessors.unpause_xbpm_feedback_and_set_transmission_to_1",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.common_flyscan_xray_centre",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.grid_detection_plan",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.create_parameters_for_flyscan_xray_centre",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.GridDetectionCallback",
        autospec=True,
    )
    @patch("bluesky.plan_stubs.sleep", autospec=True)
    def test_flyscan_xray_centre_unpauses_xbpm_feedback_on_exception(
        self,
        mock_sleep: MagicMock,
        mock_grid_detection_callback: MagicMock,
        mock_create_parameters_for_flyscan_xray_centre: MagicMock,
        mock_grid_detection_plan: MagicMock,
        mock_common_flyscan_xray_centre: MagicMock,
        mock_unpause_and_set_transmission: MagicMock,
        mock_check_and_pause: MagicMock,
        grid_detect_devices_with_oav_config_params: HyperionGridDetectThenXRayCentreComposite,
        test_full_grid_scan_params: GridScanWithEdgeDetect,
        test_config_files,
        pin_tip_detection_with_found_pin: PinTipDetection,
        RE: RunEngine,
    ):
        class TestException(Exception):
            pass

        mock_common_flyscan_xray_centre.side_effect = TestException
        with pytest.raises(TestException):  # noqa: B017
            RE(
                hyperion_grid_detect_then_xray_centre(
                    grid_detect_devices_with_oav_config_params,
                    test_full_grid_scan_params,
                    test_config_files["oav_config_json"],
                )
            )

        # Called once on exception and once on close_run
        mock_unpause_and_set_transmission.assert_has_calls([call(ANY, ANY)])

    @patch(
        "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.grid_detection_plan",
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.bps.abs_set",
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.move_aperture_if_required",
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.GridDetectionCallback",
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_grid_detect_then_xray_centre_plan.create_parameters_for_flyscan_xray_centre",
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.bps.stage",
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan.run_gridscan",
    )
    @patch(
        "mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan._fetch_xrc_results_from_zocalo",
    )
    @patch(
        "dodal.plans.preprocessors.verify_undulator_gap.verify_undulator_gap",
    )
    def test_hyperion_grid_detect_then_xray_centre_does_undulator_check_before_collection(
        self,
        mock_verify_gap: MagicMock,
        mock_fetch_zocalo_results: MagicMock,
        mock_run_gridscan: MagicMock,
        mock_bps_stage: MagicMock,
        mock_create_parameters: MagicMock,
        mock_grid_params_callback: MagicMock,
        mock_move_aperture_if_required: MagicMock,
        mock_bps_abs_set: MagicMock,
        mock_grid_detection_plan: MagicMock,
        RE: RunEngine,
        test_full_grid_scan_params: GridScanWithEdgeDetect,
        grid_detect_devices_with_oav_config_params: HyperionGridDetectThenXRayCentreComposite,
        test_config_files,
        hyperion_fgs_params,
    ):
        mock_create_parameters.return_value = hyperion_fgs_params
        mock_run_gridscan.side_effect = CompleteException
        with pytest.raises(CompleteException):
            RE(
                hyperion_grid_detect_then_xray_centre(
                    grid_detect_devices_with_oav_config_params,
                    test_full_grid_scan_params,
                    test_config_files["oav_config_json"],
                )
            )

        mock_verify_gap.assert_called_once()
