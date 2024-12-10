import types
from pathlib import Path
from unittest.mock import DEFAULT, MagicMock, call, patch

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy as np
import pytest
from bluesky.run_engine import RunEngine, RunEngineResult
from bluesky.simulators import assert_message_and_return_remaining
from bluesky.utils import FailedStatus, Msg
from dodal.beamlines import i03
from dodal.common.beamlines.beamline_utils import clear_device
from dodal.devices.aperturescatterguard import AperturePosition, ApertureValue
from dodal.devices.detector.det_dim_constants import (
    EIGER_TYPE_EIGER2_X_16M,
)
from dodal.devices.fast_grid_scan import ZebraFastGridScan
from dodal.devices.synchrotron import SynchrotronMode
from dodal.devices.zocalo import ZocaloStartInfo
from numpy import isclose
from ophyd.sim import NullStatus
from ophyd.status import Status
from ophyd_async.fastcs.panda import DatasetTable, PandaHdf5DatasetType
from ophyd_async.testing import set_mock_value

from mx_bluesky.hyperion.device_setup_plans.read_hardware_for_setup import (
    read_hardware_during_collection,
    read_hardware_pre_collection,
)
from mx_bluesky.hyperion.exceptions import WarningException
from mx_bluesky.hyperion.experiment_plans.common.xrc_result import XRayCentreResult
from mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan import (
    CrystalNotFoundException,
    FlyScanXRayCentreComposite,
    SmargonSpeedException,
    XRayCentreEventHandler,
    _FeatureControlled,
    _get_feature_controlled,
    flyscan_xray_centre,
    flyscan_xray_centre_no_move,
    kickoff_and_complete_gridscan,
    run_gridscan,
    run_gridscan_and_fetch_results,
    wait_for_gridscan_valid,
)
from mx_bluesky.hyperion.external_interaction.callbacks.common.callback_util import (
    create_gridscan_callbacks,
)
from mx_bluesky.hyperion.external_interaction.callbacks.logging_callback import (
    VerbosePlanExecutionLoggingCallback,
)
from mx_bluesky.hyperion.external_interaction.callbacks.plan_reactive_callback import (
    PlanReactiveCallback,
)
from mx_bluesky.hyperion.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
    ispyb_activation_wrapper,
)
from mx_bluesky.hyperion.external_interaction.callbacks.xray_centre.nexus_callback import (
    GridscanNexusFileCallback,
)
from mx_bluesky.hyperion.external_interaction.callbacks.zocalo_callback import (
    ZocaloCallback,
)
from mx_bluesky.hyperion.external_interaction.config_server import HyperionFeatureFlags
from mx_bluesky.hyperion.external_interaction.ispyb.ispyb_store import (
    IspybIds,
)
from mx_bluesky.hyperion.log import ISPYB_LOGGER
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.gridscan import HyperionThreeDGridScan
from tests.conftest import (
    RunEngineSimulator,
    create_dummy_scan_spec,
)

from ....conftest import simulate_xrc_result
from ....system_tests.hyperion.external_interaction.conftest import (
    TEST_RESULT_BELOW_THRESHOLD,
    TEST_RESULT_LARGE,
    TEST_RESULT_MEDIUM,
    TEST_RESULT_SMALL,
)
from ..external_interaction.callbacks.conftest import TestData
from .conftest import (
    assert_event,
    mock_zocalo_trigger,
    modified_interactor_mock,
    modified_store_grid_scan_mock,
    run_generic_ispyb_handler_setup,
)

ReWithSubs = tuple[RunEngine, tuple[GridscanNexusFileCallback, GridscanISPyBCallback]]


@pytest.fixture
def fgs_composite_with_panda_pcap(fake_fgs_composite: FlyScanXRayCentreComposite):
    capture_table = DatasetTable(name=["name"], dtype=[PandaHdf5DatasetType.FLOAT_64])
    set_mock_value(fake_fgs_composite.panda.data.datasets, capture_table)

    return fake_fgs_composite


@pytest.fixture
def fgs_params_use_panda(
    test_fgs_params: HyperionThreeDGridScan, feature_flags: HyperionFeatureFlags
):
    feature_flags.use_panda_for_gridscan = True
    test_fgs_params.features = feature_flags
    return test_fgs_params


@pytest.fixture(params=[True, False], ids=["panda", "zebra"])
def test_fgs_params_panda_zebra(
    request: pytest.FixtureRequest,
    feature_flags: HyperionFeatureFlags,
    test_fgs_params: HyperionThreeDGridScan,
):
    if request.param:
        feature_flags.use_panda_for_gridscan = request.param
    test_fgs_params.features = feature_flags
    return test_fgs_params


@pytest.fixture
def ispyb_plan(test_fgs_params: HyperionThreeDGridScan):
    @bpp.set_run_key_decorator(CONST.PLAN.GRIDSCAN_OUTER)
    @bpp.run_decorator(  # attach experiment metadata to the start document
        md={
            "subplan_name": CONST.PLAN.GRIDSCAN_OUTER,
            "hyperion_parameters": test_fgs_params.model_dump_json(),
        }
    )
    def standalone_read_hardware_for_ispyb(
        und, syn, slits, robot, attn, fl, dcm, ap_sg, sm, det
    ):
        yield from read_hardware_pre_collection(und, syn, slits, dcm, sm)
        yield from read_hardware_during_collection(ap_sg, attn, fl, dcm, det)

    return standalone_read_hardware_for_ispyb


@pytest.fixture
def RE_with_subs(
    RE: RunEngine,
    mock_subscriptions: tuple[GridscanNexusFileCallback | GridscanISPyBCallback],
):
    for cb in list(mock_subscriptions):
        RE.subscribe(cb)
    yield RE, mock_subscriptions


@pytest.fixture
def mock_ispyb():
    return MagicMock()


@pytest.fixture
def feature_controlled(
    fake_fgs_composite: FlyScanXRayCentreComposite,
    test_fgs_params_panda_zebra: HyperionThreeDGridScan,
) -> _FeatureControlled:
    return _get_feature_controlled(fake_fgs_composite, test_fgs_params_panda_zebra)


def _custom_msg(command_name: str):
    return lambda *args, **kwargs: iter([Msg(command_name)])


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.xray_centre.ispyb_callback.StoreInIspyb",
    modified_store_grid_scan_mock,
)
class TestFlyscanXrayCentrePlan:
    td: TestData = TestData()

    def test_eiger2_x_16_detector_specified(
        self,
        test_fgs_params: HyperionThreeDGridScan,
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
        fake_fgs_composite: FlyScanXRayCentreComposite,
        test_fgs_params: HyperionThreeDGridScan,
        mock_ispyb: MagicMock,
    ):
        ispyb_callback = GridscanISPyBCallback()
        RE.subscribe(ispyb_callback)

        error = None
        with pytest.raises(FailedStatus) as exc:
            with patch.object(
                fake_fgs_composite.sample_motors.omega, "set"
            ) as mock_set:
                error = AssertionError("Test Exception")
                mock_set.return_value = FailedStatus(error)

                RE(flyscan_xray_centre(fake_fgs_composite, test_fgs_params))

        assert exc.value.args[0] is error
        ispyb_callback.ispyb.end_deposition.assert_called_once_with(  # type: ignore
            IspybIds(data_collection_group_id=0, data_collection_ids=(0, 0)),
            "fail",
            "Test Exception",
        )

    def test_read_hardware_for_ispyb_updates_from_ophyd_devices(
        self,
        fake_fgs_composite: FlyScanXRayCentreComposite,
        test_fgs_params: HyperionThreeDGridScan,
        RE: RunEngine,
        ispyb_plan,
    ):
        undulator_test_value = 1.234

        set_mock_value(fake_fgs_composite.undulator.current_gap, undulator_test_value)

        synchrotron_test_value = SynchrotronMode.USER
        set_mock_value(
            fake_fgs_composite.synchrotron.synchrotron_mode, synchrotron_test_value
        )

        transmission_test_value = 0.01
        set_mock_value(
            fake_fgs_composite.attenuator.actual_transmission, transmission_test_value
        )

        current_energy_kev_test_value = 12.05
        set_mock_value(
            fake_fgs_composite.dcm.energy_in_kev.user_readback,
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
        fake_fgs_composite.s4_slit_gaps.xgap.user_readback.sim_put(xgap_test_value)  # type: ignore
        fake_fgs_composite.s4_slit_gaps.ygap.user_readback.sim_put(ygap_test_value)  # type: ignore
        flux_test_value = 10.0
        fake_fgs_composite.flux.flux_reading.sim_put(flux_test_value)  # type: ignore

        RE(
            bps.abs_set(
                fake_fgs_composite.aperture_scatterguard,
                ApertureValue.SMALL,
            )
        )

        test_ispyb_callback = PlanReactiveCallback(ISPYB_LOGGER)
        test_ispyb_callback.active = True

        with patch.multiple(
            test_ispyb_callback,
            activity_gated_start=DEFAULT,
            activity_gated_event=DEFAULT,
        ):
            RE.subscribe(test_ispyb_callback)

            RE(
                ispyb_plan(
                    fake_fgs_composite.undulator,
                    fake_fgs_composite.synchrotron,
                    fake_fgs_composite.s4_slit_gaps,
                    fake_fgs_composite.robot,
                    fake_fgs_composite.attenuator,
                    fake_fgs_composite.flux,
                    fake_fgs_composite.dcm,
                    fake_fgs_composite.aperture_scatterguard,
                    fake_fgs_composite.smargon,
                    fake_fgs_composite.eiger,
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
                    "s4_slit_gaps_xgap": xgap_test_value,
                    "s4_slit_gaps_ygap": ygap_test_value,
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
                    "flux_flux_reading": flux_test_value,
                    "dcm-energy_in_kev": current_energy_kev_test_value,
                },
            )
            # fmt: on

    @patch(
        "dodal.devices.aperturescatterguard.ApertureScatterguard._safe_move_within_datacollection_range",
        return_value=NullStatus(),
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.run_gridscan",
        autospec=True,
    )
    async def test_results_adjusted_and_event_raised(
        self,
        run_gridscan: MagicMock,
        move_aperture: MagicMock,
        fgs_composite_with_panda_pcap: FlyScanXRayCentreComposite,
        test_fgs_params_panda_zebra: HyperionThreeDGridScan,
        feature_controlled: _FeatureControlled,
        RE_with_subs: ReWithSubs,
    ):
        RE, _ = RE_with_subs

        x_ray_centre_event_handler = XRayCentreEventHandler()
        RE.subscribe(x_ray_centre_event_handler)
        mock_zocalo_trigger(fgs_composite_with_panda_pcap.zocalo, TEST_RESULT_LARGE)

        def plan():
            yield from run_gridscan_and_fetch_results(
                fgs_composite_with_panda_pcap,
                test_fgs_params_panda_zebra,
                feature_controlled,
            )

        RE(plan())

        actual = x_ray_centre_event_handler.xray_centre_results
        expected = XRayCentreResult(
            centre_of_mass_mm=np.array([0.05, 0.15, 0.25]),
            bounding_box_mm=(np.array([0.2, 0.2, 0.2]), np.array([0.8, 0.8, 0.7])),
            max_count=105062,
            total_count=2387574,
        )
        assert actual and len(actual) == 1
        assert all(isclose(actual[0].centre_of_mass_mm, expected.centre_of_mass_mm))
        assert all(isclose(actual[0].bounding_box_mm[0], expected.bounding_box_mm[0]))
        assert all(isclose(actual[0].bounding_box_mm[1], expected.bounding_box_mm[1]))

    @patch(
        "dodal.devices.aperturescatterguard.ApertureScatterguard._safe_move_within_datacollection_range",
        return_value=NullStatus(),
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.run_gridscan",
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
        run_gridscan: MagicMock,
        move_aperture: MagicMock,
        fgs_composite_with_panda_pcap: FlyScanXRayCentreComposite,
        test_fgs_params_panda_zebra: HyperionThreeDGridScan,
        RE_with_subs: ReWithSubs,
    ):
        RE, _ = RE_with_subs
        RE.subscribe(VerbosePlanExecutionLoggingCallback())

        for result in [TEST_RESULT_LARGE, TEST_RESULT_MEDIUM, TEST_RESULT_SMALL]:
            mock_zocalo_trigger(fgs_composite_with_panda_pcap.zocalo, result)
            RE(
                flyscan_xray_centre(
                    fgs_composite_with_panda_pcap,
                    test_fgs_params_panda_zebra,
                )
            )

        aperture_scatterguard = fgs_composite_with_panda_pcap.aperture_scatterguard
        large = aperture_scatterguard._loaded_positions[ApertureValue.LARGE]
        medium = aperture_scatterguard._loaded_positions[ApertureValue.MEDIUM]
        ap_call_large = call(large, ApertureValue.LARGE)
        ap_call_medium = call(medium, ApertureValue.MEDIUM)

        move_aperture.assert_has_calls([ap_call_large, ap_call_large, ap_call_medium])

        mv_to_centre = call(
            fgs_composite_with_panda_pcap.sample_motors,
            0.05,
            pytest.approx(0.15),
            0.25,
            wait=True,
        )
        move_x_y_z.assert_has_calls(
            [mv_to_centre, mv_to_centre, mv_to_centre], any_order=True
        )

    @patch("bluesky.plan_stubs.abs_set", autospec=True)
    def test_results_passed_to_move_motors(
        self,
        bps_abs_set: MagicMock,
        test_fgs_params: HyperionThreeDGridScan,
        fake_fgs_composite: FlyScanXRayCentreComposite,
        RE: RunEngine,
    ):
        from mx_bluesky.hyperion.device_setup_plans.manipulate_sample import move_x_y_z

        motor_position = test_fgs_params.FGS_params.grid_position_to_motor_position(
            np.array([1, 2, 3])
        )
        RE(move_x_y_z(fake_fgs_composite.sample_motors, *motor_position))
        bps_abs_set.assert_has_calls(
            [
                call(
                    fake_fgs_composite.sample_motors.x,
                    motor_position[0],
                    group="move_x_y_z",
                ),
                call(
                    fake_fgs_composite.sample_motors.y,
                    motor_position[1],
                    group="move_x_y_z",
                ),
                call(
                    fake_fgs_composite.sample_motors.z,
                    motor_position[2],
                    group="move_x_y_z",
                ),
            ],
            any_order=True,
        )

    @patch(
        "dodal.devices.aperturescatterguard.ApertureScatterguard._safe_move_within_datacollection_range",
        return_value=NullStatus(),
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.run_gridscan",
        autospec=True,
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.change_aperture_then_move_plan.move_x_y_z",
        autospec=True,
    )
    @patch(
        "mx_bluesky.hyperion.external_interaction.callbacks.zocalo_callback.ZocaloTrigger",
        modified_interactor_mock,
    )
    def test_individual_plans_triggered_once_and_only_once_in_composite_run(
        self,
        move_xyz: MagicMock,
        run_gridscan: MagicMock,
        move_aperture: MagicMock,
        RE_with_subs: ReWithSubs,
        fgs_composite_with_panda_pcap: FlyScanXRayCentreComposite,
        test_fgs_params_panda_zebra: HyperionThreeDGridScan,
    ):
        RE, (_, ispyb_cb) = RE_with_subs

        def wrapped_gridscan_and_move():
            yield from flyscan_xray_centre(
                fgs_composite_with_panda_pcap,
                test_fgs_params_panda_zebra,
            )

        RE(wrapped_gridscan_and_move())
        run_gridscan.assert_called_once()
        move_xyz.assert_called_once()

    @patch(
        "dodal.devices.aperturescatterguard.ApertureScatterguard.set",
        return_value=NullStatus(),
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.run_gridscan",
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
        test_fgs_params_panda_zebra: HyperionThreeDGridScan,
        fgs_composite_with_panda_pcap: FlyScanXRayCentreComposite,
        feature_controlled: _FeatureControlled,
    ):
        RE, (nexus_cb, ispyb_cb) = RE_with_subs
        test_fgs_params_panda_zebra.features.set_stub_offsets = True

        fgs_composite_with_panda_pcap.eiger.odin.fan.dev_shm_enable.sim_put(1)  # type: ignore

        def wrapped_gridscan_and_move():
            run_generic_ispyb_handler_setup(ispyb_cb, test_fgs_params_panda_zebra)
            yield from run_gridscan_and_fetch_results(
                fgs_composite_with_panda_pcap,
                test_fgs_params_panda_zebra,
                feature_controlled,
            )

        RE(
            ispyb_activation_wrapper(
                wrapped_gridscan_and_move(), test_fgs_params_panda_zebra
            )
        )
        assert fgs_composite_with_panda_pcap.eiger.odin.fan.dev_shm_enable.get() == 0

    @patch(
        "dodal.devices.aperturescatterguard.ApertureScatterguard.set",
        return_value=NullStatus(),
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.run_gridscan",
        autospec=True,
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.change_aperture_then_move_plan.move_x_y_z",
        autospec=True,
    )
    def test_when_gridscan_succeeds_ispyb_comment_appended_to(
        self,
        move_xyz: MagicMock,
        run_gridscan: MagicMock,
        aperture_set: MagicMock,
        RE_with_subs: ReWithSubs,
        test_fgs_params_panda_zebra: HyperionThreeDGridScan,
        fgs_composite_with_panda_pcap: FlyScanXRayCentreComposite,
        feature_controlled: _FeatureControlled,
    ):
        RE, (nexus_cb, ispyb_cb) = RE_with_subs

        def _wrapped_gridscan_and_move():
            run_generic_ispyb_handler_setup(ispyb_cb, test_fgs_params_panda_zebra)
            yield from run_gridscan_and_fetch_results(
                fgs_composite_with_panda_pcap,
                test_fgs_params_panda_zebra,
                feature_controlled,
            )

        RE.subscribe(VerbosePlanExecutionLoggingCallback())

        RE(
            ispyb_activation_wrapper(
                _wrapped_gridscan_and_move(), test_fgs_params_panda_zebra
            )
        )
        app_to_comment: MagicMock = ispyb_cb.ispyb.append_to_comment  # type:ignore
        app_to_comment.assert_called()
        append_aperture_call = app_to_comment.call_args_list[0].args[1]
        append_zocalo_call = app_to_comment.call_args_list[-1].args[1]
        assert "Aperture:" in append_aperture_call
        assert "Crystal 1: Strength 999999" in append_zocalo_call

    @patch(
        "mx_bluesky.common.plans.do_fgs.check_topup_and_wait_if_necessary",
    )
    def test_waits_for_motion_program(
        self,
        check_topup_and_wait,
        RE: RunEngine,
        test_fgs_params: HyperionThreeDGridScan,
        fake_fgs_composite: FlyScanXRayCentreComposite,
        done_status: Status,
    ):
        fake_fgs_composite.eiger.unstage = MagicMock(return_value=done_status)
        clear_device("zebra_fast_grid_scan")
        fgs = i03.zebra_fast_grid_scan(fake_with_ophyd_sim=True)
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
                test_fgs_params.scan_indices,
            )

        with pytest.raises(FailedStatus):
            RE(test_plan())
        fgs.KICKOFF_TIMEOUT = 1
        set_mock_value(fgs.motion_program.running, 0)
        set_mock_value(fgs.status, 1)
        res = RE(test_plan())

        assert isinstance(res, RunEngineResult)
        assert res.exit_status == "success"
        clear_device("zebra_fast_grid_scan")

    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.run_gridscan",
        autospec=True,
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.change_aperture_then_move_plan.move_x_y_z",
        autospec=True,
    )
    def test_when_gridscan_finds_no_xtal_ispyb_comment_appended_to(
        self,
        move_xyz: MagicMock,
        run_gridscan: MagicMock,
        RE_with_subs: ReWithSubs,
        test_fgs_params_panda_zebra: HyperionThreeDGridScan,
        fgs_composite_with_panda_pcap: FlyScanXRayCentreComposite,
        feature_controlled: _FeatureControlled,
    ):
        RE, (nexus_cb, ispyb_cb) = RE_with_subs

        def wrapped_gridscan_and_move():
            run_generic_ispyb_handler_setup(ispyb_cb, test_fgs_params_panda_zebra)
            yield from run_gridscan_and_fetch_results(
                fgs_composite_with_panda_pcap,
                test_fgs_params_panda_zebra,
                feature_controlled,
            )

        mock_zocalo_trigger(fgs_composite_with_panda_pcap.zocalo, [])
        with pytest.raises(CrystalNotFoundException):
            RE(
                ispyb_activation_wrapper(
                    wrapped_gridscan_and_move(), test_fgs_params_panda_zebra
                )
            )

        app_to_comment: MagicMock = ispyb_cb.ispyb.append_to_comment  # type:ignore
        app_to_comment.assert_called()
        append_aperture_call = app_to_comment.call_args_list[0].args[1]
        append_zocalo_call = app_to_comment.call_args_list[-1].args[1]
        assert "Aperture:" in append_aperture_call
        assert "Zocalo found no crystals in this gridscan" in append_zocalo_call

    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.run_gridscan",
        autospec=True,
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.change_aperture_then_move_plan.move_x_y_z",
        autospec=True,
    )
    def test_when_gridscan_finds_no_xtal_exception_is_raised(
        self,
        move_xyz: MagicMock,
        run_gridscan: MagicMock,
        RE_with_subs: ReWithSubs,
        test_fgs_params_panda_zebra: HyperionThreeDGridScan,
        fgs_composite_with_panda_pcap: FlyScanXRayCentreComposite,
        feature_controlled: _FeatureControlled,
    ):
        RE, (nexus_cb, ispyb_cb) = RE_with_subs

        def wrapped_gridscan_and_move():
            run_generic_ispyb_handler_setup(ispyb_cb, test_fgs_params_panda_zebra)
            yield from run_gridscan_and_fetch_results(
                fgs_composite_with_panda_pcap,
                test_fgs_params_panda_zebra,
                feature_controlled,
            )

        mock_zocalo_trigger(fgs_composite_with_panda_pcap.zocalo, [])
        with pytest.raises(CrystalNotFoundException):
            RE(
                ispyb_activation_wrapper(
                    wrapped_gridscan_and_move(), test_fgs_params_panda_zebra
                )
            )

    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.bps.sleep",
        autospec=True,
    )
    def test_GIVEN_scan_already_valid_THEN_wait_for_GRIDSCAN_returns_immediately(
        self, patch_sleep: MagicMock, RE: RunEngine
    ):
        test_fgs: ZebraFastGridScan = i03.zebra_fast_grid_scan(fake_with_ophyd_sim=True)

        set_mock_value(test_fgs.position_counter, 0)
        set_mock_value(test_fgs.scan_invalid, False)

        RE(wait_for_gridscan_valid(test_fgs))

        patch_sleep.assert_not_called()

    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.bps.sleep",
        autospec=True,
    )
    def test_GIVEN_scan_not_valid_THEN_wait_for_GRIDSCAN_raises_and_sleeps_called(
        self, patch_sleep: MagicMock, RE: RunEngine
    ):
        test_fgs: ZebraFastGridScan = i03.zebra_fast_grid_scan(fake_with_ophyd_sim=True)

        set_mock_value(test_fgs.scan_invalid, True)
        set_mock_value(test_fgs.position_counter, 0)

        with pytest.raises(WarningException):
            RE(wait_for_gridscan_valid(test_fgs))

        patch_sleep.assert_called()

    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.bps.abs_set",
        autospec=True,
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.bps.kickoff",
        autospec=True,
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.bps.complete",
        autospec=True,
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.bps.mv",
        autospec=True,
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.wait_for_gridscan_valid",
        autospec=True,
    )
    @patch(
        "mx_bluesky.hyperion.external_interaction.nexus.write_nexus.NexusWriter",
        autospec=True,
        spec_set=True,
    )
    @patch(
        "mx_bluesky.common.plans.do_fgs.check_topup_and_wait_if_necessary",
        autospec=True,
    )
    def test_when_grid_scan_ran_then_eiger_disarmed_before_zocalo_end(
        self,
        mock_check_topup,
        nexuswriter,
        wait_for_valid,
        mock_mv,
        mock_complete,
        mock_kickoff,
        mock_abs_set,
        fake_fgs_composite: FlyScanXRayCentreComposite,
        test_fgs_params: HyperionThreeDGridScan,
        RE_with_subs: ReWithSubs,
    ):
        test_fgs_params.x_steps = 9
        test_fgs_params.y_steps = 10
        test_fgs_params.z_steps = 12
        RE, (nexus_cb, ispyb_cb) = RE_with_subs
        # Put both mocks in a parent to easily capture order
        mock_parent = MagicMock()
        fake_fgs_composite.eiger.disarm_detector = mock_parent.disarm

        fake_fgs_composite.eiger.filewriters_finished = NullStatus()  # type: ignore
        fake_fgs_composite.eiger.odin.check_and_wait_for_odin_state = MagicMock(
            return_value=True
        )
        fake_fgs_composite.eiger.odin.file_writer.num_captured.sim_put(1200)  # type: ignore
        fake_fgs_composite.eiger.stage = MagicMock(
            return_value=Status(None, None, 0, True, True)
        )
        set_mock_value(fake_fgs_composite.xbpm_feedback.pos_stable, True)

        with (
            patch(
                "mx_bluesky.hyperion.external_interaction.callbacks.xray_centre.nexus_callback.NexusWriter.create_nexus_file",
                autospec=True,
            ),
            patch(
                "mx_bluesky.hyperion.external_interaction.callbacks.zocalo_callback.ZocaloTrigger",
                lambda _: modified_interactor_mock(mock_parent.run_end),
            ),
        ):
            [RE.subscribe(cb) for cb in (nexus_cb, ispyb_cb)]
            RE(flyscan_xray_centre(fake_fgs_composite, test_fgs_params))

        mock_parent.assert_has_calls([call.disarm(), call.run_end(0), call.run_end(0)])

    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.set_panda_directory",
        side_effect=_custom_msg("set_panda_directory"),
    )
    @patch(
        "mx_bluesky.hyperion.device_setup_plans.setup_panda.arm_panda_for_gridscan",
        new=MagicMock(side_effect=_custom_msg("arm_panda")),
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.disarm_panda_for_gridscan",
        new=MagicMock(side_effect=_custom_msg("disarm_panda")),
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.run_gridscan",
        new=MagicMock(side_effect=_custom_msg("do_gridscan")),
    )
    def test_flyscan_xray_centre_sets_directory_stages_arms_disarms_unstages_the_panda(
        self,
        mock_set_panda_directory: MagicMock,
        done_status: Status,
        fgs_composite_with_panda_pcap: FlyScanXRayCentreComposite,
        fgs_params_use_panda: HyperionThreeDGridScan,
        sim_run_engine: RunEngineSimulator,
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
                fgs_composite_with_panda_pcap, fgs_params_use_panda
            )
        )

        mock_set_panda_directory.assert_called_with(
            Path("/tmp/dls/i03/data/2024/cm31105-4/xraycentring/123456")
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

    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.bps.wait",
        autospec=True,
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.bps.complete",
        autospec=True,
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.bps.kickoff",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.plans.do_fgs.check_topup_and_wait_if_necessary",
        autospec=True,
    )
    def test_fgs_arms_eiger_without_grid_detect(
        self,
        mock_topup,
        mock_kickoff,
        mock_complete,
        mock_wait,
        fake_fgs_composite: FlyScanXRayCentreComposite,
        test_fgs_params_panda_zebra: HyperionThreeDGridScan,
        RE: RunEngine,
        done_status: Status,
        feature_controlled: _FeatureControlled,
    ):
        fake_fgs_composite.eiger.unstage = MagicMock(return_value=done_status)
        RE(
            run_gridscan(
                fake_fgs_composite, test_fgs_params_panda_zebra, feature_controlled
            )
        )
        fake_fgs_composite.eiger.stage.assert_called_once()  # type: ignore
        fake_fgs_composite.eiger.unstage.assert_called_once()

    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.bps.kickoff",
        autospec=True,
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.bps.wait",
        autospec=True,
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.bps.complete",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.plans.do_fgs.check_topup_and_wait_if_necessary",
        autospec=True,
    )
    def test_when_grid_scan_fails_with_exception_then_detector_disarmed_and_correct_exception_returned(
        self,
        mock_topup,
        mock_complete,
        mock_wait,
        mock_kickoff,
        fake_fgs_composite: FlyScanXRayCentreComposite,
        test_fgs_params_panda_zebra: HyperionThreeDGridScan,
        RE: RunEngine,
        feature_controlled: _FeatureControlled,
    ):
        class CompleteException(Exception):
            pass

        mock_complete.side_effect = CompleteException()

        fake_fgs_composite.eiger.stage = MagicMock(
            return_value=Status(None, None, 0, True, True)
        )

        fake_fgs_composite.eiger.filewriters_finished = NullStatus()

        fake_fgs_composite.eiger.odin.check_and_wait_for_odin_state = MagicMock()

        fake_fgs_composite.eiger.disarm_detector = MagicMock()
        fake_fgs_composite.eiger.disable_roi_mode = MagicMock()

        with pytest.raises(CompleteException):
            RE(
                run_gridscan(
                    fake_fgs_composite, test_fgs_params_panda_zebra, feature_controlled
                )
            )

        fake_fgs_composite.eiger.disable_roi_mode.assert_called()
        fake_fgs_composite.eiger.disarm_detector.assert_called()

    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.bps.kickoff",
        autospec=True,
    )
    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.bps.complete",
        autospec=True,
    )
    @patch(
        "mx_bluesky.hyperion.external_interaction.callbacks.zocalo_callback.ZocaloTrigger",
        autospec=True,
    )
    @patch(
        "mx_bluesky.common.plans.do_fgs.check_topup_and_wait_if_necessary",
        autospec=True,
    )
    def test_kickoff_and_complete_gridscan_triggers_zocalo(
        self,
        mock_topup,
        mock_zocalo_trigger_class: MagicMock,
        mock_complete: MagicMock,
        mock_kickoff: MagicMock,
        RE: RunEngine,
        fake_fgs_composite: FlyScanXRayCentreComposite,
    ):
        id_1, id_2 = 100, 200

        _, ispyb_cb = create_gridscan_callbacks()
        ispyb_cb.active = True
        ispyb_cb.ispyb = MagicMock()
        ispyb_cb.params = MagicMock()
        ispyb_cb.ispyb_ids.data_collection_ids = (id_1, id_2)
        assert isinstance(ispyb_cb.emit_cb, ZocaloCallback)
        zocalo_env = "dev_env"

        mock_zocalo_trigger_class.return_value = (mock_zocalo_trigger := MagicMock())

        fake_fgs_composite.eiger.unstage = MagicMock()
        fake_fgs_composite.eiger.odin.file_writer.id.sim_put("test/filename")  # type: ignore

        x_steps, y_steps, z_steps = 10, 20, 30

        RE.subscribe(ispyb_cb)

        RE(
            kickoff_and_complete_gridscan(
                fake_fgs_composite.zebra_fast_grid_scan,
                fake_fgs_composite.eiger,
                fake_fgs_composite.synchrotron,
                scan_points=create_dummy_scan_spec(x_steps, y_steps, z_steps),
                scan_start_indices=[0, x_steps * y_steps],
                zocalo_environment=zocalo_env,
            )
        )
        mock_zocalo_trigger_class.assert_called_once_with(zocalo_env)

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

        assert mock_zocalo_trigger.run_start.call_count == 2
        assert mock_zocalo_trigger.run_start.mock_calls == expected_start_calls

        assert mock_zocalo_trigger.run_end.call_count == 2
        assert mock_zocalo_trigger.run_end.mock_calls == [call(id_1), call(id_2)]

    @patch(
        "mx_bluesky.common.plans.do_fgs.check_topup_and_wait_if_necessary",
        new=MagicMock(side_effect=lambda *_, **__: iter([Msg("check_topup")])),
    )
    def test_read_hardware_during_collection_occurs_after_eiger_arm(
        self,
        fake_fgs_composite: FlyScanXRayCentreComposite,
        test_fgs_params_panda_zebra: HyperionThreeDGridScan,
        sim_run_engine: RunEngineSimulator,
        feature_controlled: _FeatureControlled,
    ):
        sim_run_engine.add_handler(
            "read",
            lambda msg: {"values": {"value": SynchrotronMode.USER}},
            "synchrotron-synchrotron_mode",
        )
        msgs = sim_run_engine.simulate_plan(
            run_gridscan(
                fake_fgs_composite, test_fgs_params_panda_zebra, feature_controlled
            )
        )
        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "stage" and msg.obj.name == "eiger"
        )
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "kickoff"
            and msg.obj == feature_controlled.fgs_motors,
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
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.kickoff_and_complete_gridscan",
    )
    def test_if_smargon_speed_over_limit_then_log_error(
        self,
        mock_kickoff_and_complete: MagicMock,
        test_fgs_params_panda_zebra: HyperionThreeDGridScan,
        fake_fgs_composite: FlyScanXRayCentreComposite,
        feature_controlled: _FeatureControlled,
        RE: RunEngine,
    ):
        test_fgs_params_panda_zebra.x_step_size_um = 10000
        test_fgs_params_panda_zebra.detector_params.exposure_time = 0.01

        # this exception should only be raised if we're using the panda
        try:
            RE(
                run_gridscan_and_fetch_results(
                    fake_fgs_composite, test_fgs_params_panda_zebra, feature_controlled
                )
            )
        except SmargonSpeedException:
            assert test_fgs_params_panda_zebra.features.use_panda_for_gridscan
        else:
            assert not test_fgs_params_panda_zebra.features.use_panda_for_gridscan

    @patch(
        "mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan.kickoff_and_complete_gridscan",
        MagicMock(),
    )
    def test_run_gridscan_and_fetch_results_discards_results_below_threshold(
        self,
        fake_fgs_composite: FlyScanXRayCentreComposite,
        test_fgs_params_panda_zebra: HyperionThreeDGridScan,
        feature_controlled: _FeatureControlled,
        RE: RunEngine,
    ):
        callback = XRayCentreEventHandler()
        RE.subscribe(callback)

        mock_zocalo_trigger(
            fake_fgs_composite.zocalo,
            TEST_RESULT_MEDIUM + TEST_RESULT_BELOW_THRESHOLD + TEST_RESULT_SMALL,
        )
        RE(
            run_gridscan_and_fetch_results(
                fake_fgs_composite, test_fgs_params_panda_zebra, feature_controlled
            )
        )

        assert callback.xray_centre_results and len(callback.xray_centre_results) == 2
        assert [r.max_count for r in callback.xray_centre_results] == [50000, 1000]
