import re

import bluesky.preprocessors as bpp
import numpy as np
import pytest
from bluesky.run_engine import RunEngine
from dodal.devices.eiger import EigerDetector
from dodal.devices.zocalo import ZocaloResults
from dodal.utils import is_test_mode

from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    ispyb_activation_wrapper,
)
from mx_bluesky.common.parameters.constants import (
    EnvironmentConstants,
    PlanNameConstants,
)
from mx_bluesky.common.plans.read_hardware import read_hardware_for_zocalo
from mx_bluesky.hyperion.external_interaction.callbacks.__main__ import (
    create_gridscan_callbacks,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.gridscan import HyperionSpecifiedThreeDGridScan
from tests.conftest import create_dummy_scan_spec

"""
If fake-zocalo system tests are failing, check that the RMQ instance is set up right:

- Open the RMQ webpage specified when you start the fake zocalo and login with the
provided credentials

- go to the admin panel and under the 'exchanges' tab ensure that there is a 'results'
exchange for the zocalo vhost (other settings can be left blank)

- go to the 'queues and streams' tab and add a binding for the xrc.i03 queue to the
results exchange, with the routing key 'xrc.i03'

- make sure that there are no un-acked/un-delivered messages on the i03.xrc queue
"""


@bpp.set_run_key_decorator("testing125")
@bpp.run_decorator(
    md={
        "subplan_name": PlanNameConstants.DO_FGS,
        "zocalo_environment": EnvironmentConstants.ZOCALO_ENV,
        "scan_points": create_dummy_scan_spec(10, 20, 30),
    }
)
def fake_fgs_plan(eiger: EigerDetector):
    yield from read_hardware_for_zocalo(eiger)


@pytest.fixture
def run_zocalo_with_dev_ispyb(
    dummy_params: HyperionSpecifiedThreeDGridScan,
    dummy_ispyb,
    RE: RunEngine,
    zocalo_for_fake_zocalo: ZocaloResults,
    eiger: EigerDetector,
):
    async def inner(sample_name="", fallback=np.array([0, 0, 0])):
        dummy_params.file_name = sample_name
        _, ispyb_callback = create_gridscan_callbacks()
        RE.subscribe(ispyb_callback)

        @bpp.set_run_key_decorator("testing123")
        def trigger_zocalo_after_fast_grid_scan():
            @bpp.set_run_key_decorator("testing124")
            @bpp.stage_decorator([zocalo_for_fake_zocalo])
            @bpp.run_decorator(
                md={
                    "subplan_name": CONST.PLAN.GRIDSCAN_OUTER,
                    "zocalo_environment": EnvironmentConstants.ZOCALO_ENV,
                    "mx_bluesky_parameters": dummy_params.model_dump_json(),
                }
            )
            def inner_plan():
                yield from fake_fgs_plan(eiger)

            yield from inner_plan()

        RE(
            ispyb_activation_wrapper(
                trigger_zocalo_after_fast_grid_scan(), dummy_params
            )
        )
        centre = await zocalo_for_fake_zocalo.centre_of_mass.get_value()
        if centre.size == 0:
            centre = fallback
        else:
            centre = centre[0]

        return ispyb_callback, ispyb_callback.emit_cb, centre

    return inner


@pytest.mark.system_test
def test_is_test_mode():
    assert is_test_mode(), "DODAL_TEST_MODE must be set in environment before launch"


@pytest.mark.system_test
async def test_given_a_result_with_no_diffraction_when_zocalo_called_then_move_to_fallback(
    run_zocalo_with_dev_ispyb,
):
    fallback = np.array([1, 2, 3])
    _, _, centre = await run_zocalo_with_dev_ispyb("NO_DIFF", fallback)
    assert np.allclose(centre, fallback)


@pytest.mark.system_test
async def test_zocalo_adds_nonzero_comment_time(
    run_zocalo_with_dev_ispyb, fetch_comment
):
    ispyb, zc, _ = await run_zocalo_with_dev_ispyb()

    comment = fetch_comment(ispyb.ispyb_ids.data_collection_ids[0])
    match = re.match(r".*Zocalo processing took (\d+\.\d+) s", comment)
    assert match
    time_s = float(match.group(1))
    assert time_s > 0
    assert time_s < 180
