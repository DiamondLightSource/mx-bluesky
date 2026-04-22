from collections.abc import Generator, Sequence
from typing import Any

import bluesky.plan_stubs as bps
from dodal.devices.smargon import Smargon, StubPosition
from dodal.devices.zocalo import ZocaloResults

from mx_bluesky.common.device_setup_plans.manipulate_sample import move_x_y_z
from mx_bluesky.common.experiment_plans.inner_plans.xrc_results_utils import (
    fetch_xrc_results_from_zocalo,
)
from mx_bluesky.common.parameters.device_composites import (
    GridDetectThenXRayCentreComposite,
)
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.utils.tracing import TRACER
from mx_bluesky.common.utils.xrc_result import XRayCentreEventHandler, XRayCentreResult


def _get_xrc_results(
    zocalo: ZocaloResults,
    parameters: SpecifiedThreeDGridScan,
    flyscan_event_handler: XRayCentreEventHandler,
) -> Generator[Any, Any, Sequence[XRayCentreResult]]:
    yield from fetch_xrc_results_from_zocalo(zocalo, parameters)
    flyscan_results = flyscan_event_handler.xray_centre_results
    assert flyscan_results, (
        "Flyscan result event not received or no crystal found and exception not raised"
    )
    return flyscan_results


def get_results_and_move_to_xtal(
    composite: GridDetectThenXRayCentreComposite,
    parameters: SpecifiedThreeDGridScan,
    flyscan_event_handler: XRayCentreEventHandler,
):
    flyscan_results = yield from _get_xrc_results(
        composite.zocalo, parameters, flyscan_event_handler
    )
    yield from move_to_xtal(flyscan_results[0], composite.gonio)


def move_to_xtal(
    best_hit: XRayCentreResult,
    smargon: Smargon,
    set_stub_offsets: bool | None = None,
):
    """For the given x-ray centring result,
    * Centre on the centre-of-mass
    * Reset the stub offsets if specified by params
    """
    LOGGER.info("Moving to centre of mass.")
    with TRACER.start_span("move_to_result"):
        x, y, z = best_hit.centre_of_mass_mm
        yield from move_x_y_z(smargon, x, y, z, wait=True)

    # TODO support for setting stub offsets in multipin
    # https://github.com/DiamondLightSource/mx-bluesky/issues/552
    if set_stub_offsets:
        LOGGER.info("Recentring smargon co-ordinate system to this point.")
        yield from bps.mv(smargon.stub_offsets, StubPosition.CURRENT_AS_CENTER)
