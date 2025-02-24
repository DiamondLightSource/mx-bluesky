from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import assert_message_and_return_remaining
from bluesky.utils import Msg
from dodal.devices.aperturescatterguard import (
    ApertureValue,
)
from ophyd.sim import NullStatus
from ophyd.status import Status
from ophyd_async.fastcs.panda import DatasetTable, PandaHdf5DatasetType
from ophyd_async.testing import set_mock_value

from mx_bluesky.common.external_interaction.callbacks.common.logging_callback import (
    VerbosePlanExecutionLoggingCallback,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
    ispyb_activation_wrapper,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.nexus_callback import (
    GridscanNexusFileCallback,
)
from mx_bluesky.common.parameters.constants import DeviceSettingsConstants
from mx_bluesky.common.plans.common_flyscan_xray_centre_plan import (
    BeamlineSpecificFGSFeatures,
    FlyScanEssentialDevices,
    flyscan_xray_centre_no_move,
    highest_level_flyscan_xray_centre,
    run_gridscan_and_fetch_results,
)
from mx_bluesky.hyperion.experiment_plans.hyperion_flyscan_xray_centre_plan import (
    SmargonSpeedException,
    construct_hyperion_specific_features,
)
from mx_bluesky.hyperion.external_interaction.config_server import HyperionFeatureFlags
from mx_bluesky.hyperion.parameters.device_composites import (
    HyperionFlyScanXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import HyperionSpecifiedThreeDGridScan
from tests.conftest import (
    RunEngineSimulator,
)

from ....conftest import TEST_RESULT_LARGE, TestData, simulate_xrc_result
from ...conftest import (
    mock_zocalo_trigger,
    modified_store_grid_scan_mock,
    run_generic_ispyb_handler_setup,
)

ReWithSubs = tuple[RunEngine, tuple[GridscanNexusFileCallback, GridscanISPyBCallback]]


@pytest.fixture
def fgs_params_use_panda(
    test_fgs_params: HyperionSpecifiedThreeDGridScan,
    feature_flags: HyperionFeatureFlags,
):
    feature_flags.use_panda_for_gridscan = True
    test_fgs_params.features = feature_flags
    return test_fgs_params


@pytest.fixture
def feature_controlled(
    fake_fgs_composite: HyperionFlyScanXRayCentreComposite,
    test_fgs_params: HyperionSpecifiedThreeDGridScan,
) -> BeamlineSpecificFGSFeatures:
    return construct_hyperion_specific_features(fake_fgs_composite, test_fgs_params)


def _custom_msg(command_name: str):
    return lambda *args, **kwargs: iter([Msg(command_name)])


@pytest.fixture
def fgs_composite_with_panda_pcap(
    fake_fgs_composite: HyperionFlyScanXRayCentreComposite,
):
    capture_table = DatasetTable(name=["name"], dtype=[PandaHdf5DatasetType.FLOAT_64])
    set_mock_value(fake_fgs_composite.panda.data.datasets, capture_table)

    return fake_fgs_composite


@patch(
    "mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback.StoreInIspyb",
    modified_store_grid_scan_mock,
)
class TestFlyscanXrayCentrePlan:
    @patch(
        "dodal.devices.aperturescatterguard.ApertureScatterguard._safe_move_within_datacollection_range",
        return_value=NullStatus(),
    )
    @patch(
        "mx_bluesky.common.plans.common_flyscan_xray_centre_plan.run_gridscan",
        autospec=True,
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.change_aperture_then_move_plan.move_x_y_z",
        autospec=True,
    )
    @pytest.mark.skip(
        reason="TODO mx-bluesky 231 aperture size should be determined from absolute size not box size"
    )
    def test_results_adjusted_and_passed_to_move_xyz(
        self,
        move_x_y_z: MagicMock,
        move_aperture: MagicMock,
        run_gridscan: MagicMock,
        fake_fgs_composite: HyperionFlyScanXRayCentreComposite,
        test_fgs_params: HyperionSpecifiedThreeDGridScan,
        RE_with_subs: ReWithSubs,
        feature_controlled: BeamlineSpecificFGSFeatures,
    ):
        RE, _ = RE_with_subs
        RE.subscribe(VerbosePlanExecutionLoggingCallback())

        for result in [
            TestData.test_result_large,
            TestData.test_result_medium,
            TestData.test_result_small,
        ]:
            mock_zocalo_trigger(fake_fgs_composite.zocalo, result)
            RE(
                highest_level_flyscan_xray_centre(
                    fake_fgs_composite,
                    test_fgs_params,
                    feature_controlled,
                )
            )

        aperture_scatterguard = fake_fgs_composite.aperture_scatterguard
        large = aperture_scatterguard._loaded_positions[ApertureValue.LARGE]
        medium = aperture_scatterguard._loaded_positions[ApertureValue.MEDIUM]
        ap_call_large = call(large, ApertureValue.LARGE)
        ap_call_medium = call(medium, ApertureValue.MEDIUM)

        move_aperture.assert_has_calls([ap_call_large, ap_call_large, ap_call_medium])

        mv_to_centre = call(
            fake_fgs_composite.smargon,
            0.05,
            pytest.approx(0.15),
            0.25,
            wait=True,
        )
        move_x_y_z.assert_has_calls(
            [mv_to_centre, mv_to_centre, mv_to_centre], any_order=True
        )

    @patch(
        "dodal.devices.aperturescatterguard.ApertureScatterguard.set",
        return_value=NullStatus(),
    )
    @patch(
        "mx_bluesky.common.plans.common_flyscan_xray_centre_plan.run_gridscan",
        autospec=True,
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.change_aperture_then_move_plan.move_x_y_z",
        autospec=True,
    )
    async def test_when_gridscan_finished_then_dev_shm_disabled(
        self,
        move_xyz: MagicMock,
        run_gridscan: MagicMock,
        aperture_set: MagicMock,
        RE_with_subs: ReWithSubs,
        test_fgs_params: HyperionSpecifiedThreeDGridScan,
        fake_fgs_composite: FlyScanEssentialDevices,
        feature_controlled: BeamlineSpecificFGSFeatures,
    ):
        RE, (nexus_cb, ispyb_cb) = RE_with_subs
        test_fgs_params.features.set_stub_offsets = True

        fake_fgs_composite.eiger.odin.fan.dev_shm_enable.sim_put(1)  # type: ignore

        def wrapped_gridscan_and_move():
            run_generic_ispyb_handler_setup(ispyb_cb, test_fgs_params)
            yield from run_gridscan_and_fetch_results(
                fake_fgs_composite,
                test_fgs_params,
                feature_controlled,
            )

        RE(ispyb_activation_wrapper(wrapped_gridscan_and_move(), test_fgs_params))
        assert fake_fgs_composite.eiger.odin.fan.dev_shm_enable.get() == 0

    @patch(
        "mx_bluesky.common.plans.common_flyscan_xray_centre_plan.kickoff_and_complete_gridscan",
    )
    def test_if_smargon_speed_over_limit_then_log_error(
        self,
        mock_kickoff_and_complete: MagicMock,
        test_fgs_params: HyperionSpecifiedThreeDGridScan,
        fake_fgs_composite: FlyScanEssentialDevices,
        feature_controlled: BeamlineSpecificFGSFeatures,
        RE: RunEngine,
    ):
        test_fgs_params.x_step_size_um = 10000
        test_fgs_params.detector_params.exposure_time = 0.01

        # this exception should only be raised if we're using the panda
        try:
            RE(
                run_gridscan_and_fetch_results(
                    fake_fgs_composite, test_fgs_params, feature_controlled
                )
            )
        except SmargonSpeedException:
            assert test_fgs_params.features.use_panda_for_gridscan
        else:
            assert not test_fgs_params.features.use_panda_for_gridscan

    @patch(
        "mx_bluesky.hyperion.experiment_plans.hyperion_flyscan_xray_centre_plan.set_panda_directory",
        side_effect=_custom_msg("set_panda_directory"),
    )
    @patch(
        "mx_bluesky.hyperion.device_setup_plans.setup_panda.arm_panda_for_gridscan",
        new=MagicMock(side_effect=_custom_msg("arm_panda")),
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.hyperion_flyscan_xray_centre_plan.disarm_panda_for_gridscan",
        new=MagicMock(side_effect=_custom_msg("disarm_panda")),
    )
    @patch(
        "mx_bluesky.common.plans.common_flyscan_xray_centre_plan.run_gridscan",
        new=MagicMock(side_effect=_custom_msg("do_gridscan")),
    )
    @patch("mx_bluesky.hyperion.device_setup_plans.setup_panda.load_panda_from_yaml")
    def test_flyscan_xray_centre_sets_directory_stages_arms_disarms_unstages_the_panda(
        self,
        mock_load_panda: MagicMock,
        mock_set_panda_directory: MagicMock,
        done_status: Status,
        fgs_composite_with_panda_pcap: HyperionFlyScanXRayCentreComposite,
        fgs_params_use_panda: HyperionSpecifiedThreeDGridScan,
        sim_run_engine: RunEngineSimulator,
        feature_controlled: BeamlineSpecificFGSFeatures,
    ):
        sim_run_engine.add_handler("unstage", lambda _: done_status)
        sim_run_engine.add_read_handler_for(
            fgs_composite_with_panda_pcap.smargon.x.max_velocity, 10
        )
        simulate_xrc_result(
            sim_run_engine, fgs_composite_with_panda_pcap.zocalo, TEST_RESULT_LARGE
        )

        msgs = sim_run_engine.simulate_plan(
            flyscan_xray_centre_no_move(
                fgs_composite_with_panda_pcap, fgs_params_use_panda, feature_controlled
            )
        )

        mock_set_panda_directory.assert_called_with(
            Path("/tmp/dls/i03/data/2024/cm31105-4/xraycentring/123456")
        )
        mock_load_panda.assert_called_once_with(
            DeviceSettingsConstants.PANDA_FLYSCAN_SETTINGS_DIR,
            DeviceSettingsConstants.PANDA_FLYSCAN_SETTINGS_FILENAME,
            fgs_composite_with_panda_pcap.panda,
        )

        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "set_panda_directory"
        )
        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "stage" and msg.obj.name == "panda"
        )
        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "arm_panda"
        )
        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "do_gridscan"
        )
        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "disarm_panda"
        )
        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "unstage" and msg.obj.name == "panda"
        )
