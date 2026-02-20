import bluesky.plan_stubs as bps
import numpy as np
import pytest
from bluesky.run_engine import RunEngine
from bluesky.simulators import assert_message_and_return_remaining
from dodal.devices.zocalo import ZocaloResults

from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    BeamlineSpecificFGSFeatures,
    FlyScanEssentialDevices,
)
from mx_bluesky.common.experiment_plans.inner_plans.do_fgs import ZOCALO_STAGE_GROUP
from mx_bluesky.common.experiment_plans.inner_plans.xrc_results_utils import (
    fetch_xrc_results_from_zocalo,
    zocalo_stage_decorator,
)
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
from mx_bluesky.common.utils.exceptions import (
    CrystalNotFoundError,
)
from mx_bluesky.common.utils.xrc_result import XRayCentreEventHandler, XRayCentreResult
from tests.conftest import (
    RunEngineSimulator,
)
from tests.unit_tests.hyperion.experiment_plans.conftest import (
    mock_zocalo_trigger,
)

from ....conftest import TestData

""" Below are tests for getting zocalo results from the zocalo device, which is done
 post gridscan """


async def test_results_adjusted_and_event_raised(
    test_three_d_grid_params: SpecifiedThreeDGridScan,
    run_engine: RunEngine,
    zocalo: ZocaloResults,
):
    x_ray_centre_event_handler = XRayCentreEventHandler()
    run_engine.subscribe(x_ray_centre_event_handler)
    mock_zocalo_trigger(zocalo, TestData.test_result_large)
    run_engine(fetch_xrc_results_from_zocalo(zocalo, test_three_d_grid_params))

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
    assert all(np.isclose(actual[0].centre_of_mass_mm, expected.centre_of_mass_mm))
    assert all(np.isclose(actual[0].bounding_box_mm[0], expected.bounding_box_mm[0]))
    assert all(np.isclose(actual[0].bounding_box_mm[1], expected.bounding_box_mm[1]))


def test_fetch_results_discards_results_below_threshold(
    test_three_d_grid_params: SpecifiedThreeDGridScan,
    run_engine: RunEngine,
    zocalo: ZocaloResults,
):
    callback = XRayCentreEventHandler()
    run_engine.subscribe(callback)

    mock_zocalo_trigger(
        zocalo,
        TestData.test_result_medium
        + TestData.test_result_below_threshold
        + TestData.test_result_small,
    )
    run_engine(fetch_xrc_results_from_zocalo(zocalo, test_three_d_grid_params))

    assert callback.xray_centre_results and len(callback.xray_centre_results) == 2
    assert [r.max_count for r in callback.xray_centre_results] == [50000, 1000]


def test_no_xtal_found_raises_exception(
    run_engine: RunEngine,
    test_three_d_grid_params: SpecifiedThreeDGridScan,
    zocalo: ZocaloResults,
):
    mock_zocalo_trigger(zocalo, [])

    with pytest.raises(CrystalNotFoundError):
        run_engine(fetch_xrc_results_from_zocalo(zocalo, test_three_d_grid_params))


def test_dummy_result_returned_when_no_xtal_and_commissioning_mode_enabled(
    run_engine: RunEngine,
    test_three_d_grid_params: SpecifiedThreeDGridScan,
    fake_fgs_composite: FlyScanEssentialDevices,
    beamline_specific: BeamlineSpecificFGSFeatures,
    zocalo: ZocaloResults,
    baton_in_commissioning_mode,
):
    xrc_event_handler = XRayCentreEventHandler()
    run_engine.subscribe(xrc_event_handler)

    mock_zocalo_trigger(zocalo, [])

    run_engine(fetch_xrc_results_from_zocalo(zocalo, test_three_d_grid_params))
    results = xrc_event_handler.xray_centre_results or []
    assert len(results) == 1
    result = results[0]
    assert result.sample_id == test_three_d_grid_params.sample_id
    assert result.max_count == 10000
    assert result.total_count == 100000
    assert all(np.isclose(result.bounding_box_mm[0], [1.95, 0.95, 0.45]))
    assert all(np.isclose(result.bounding_box_mm[1], [2.05, 1.05, 0.55]))
    assert all(np.isclose(result.centre_of_mass_mm, [2.0, 1.0, 0.5]))


def test_zocalo_stage_wrapper(
    zocalo: ZocaloResults, sim_run_engine: RunEngineSimulator
):
    @zocalo_stage_decorator(zocalo)
    def test_plan():
        yield from bps.null()

    msgs = sim_run_engine.simulate_plan(test_plan())
    msgs = assert_message_and_return_remaining(
        msgs,
        predicate=lambda msg: msg.command == "stage"
        and msg.obj.name == "zocalo"
        and msg.kwargs["group"] == ZOCALO_STAGE_GROUP,
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        predicate=lambda msg: msg.command == "unstage" and msg.obj.name == "zocalo",
    )
