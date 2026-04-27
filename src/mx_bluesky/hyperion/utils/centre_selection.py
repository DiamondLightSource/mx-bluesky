from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from functools import partial

import numpy as np
from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.devices.smargon import Smargon

from mx_bluesky.common.utils import xrc_result as flyscan_result
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.utils.xrc_result import XRayCentreResult
from mx_bluesky.hyperion.blueapi.mixins import (
    MultiXtalSelection,
    TopNByMaxCountForEachSampleSelection,
    TopNByMaxCountSelection,
)


def top_n_by_max_count(
    unfiltered: Sequence[XRayCentreResult], n: int
) -> Sequence[XRayCentreResult]:
    sorted_hits = sorted(unfiltered, key=lambda result: result.max_count, reverse=True)
    return sorted_hits[:n]


def top_n_by_max_count_for_each_sample(
    unfiltered: Sequence[XRayCentreResult], n: int
) -> Sequence[XRayCentreResult]:
    xrc_results_by_sample_id: dict[int | None, list[XRayCentreResult]] = defaultdict(
        list[XRayCentreResult]
    )
    for result in unfiltered:
        xrc_results_by_sample_id[result.sample_id].append(result)
    return [
        result
        for results in xrc_results_by_sample_id.values()
        for result in sorted(results, key=lambda x: x.max_count, reverse=True)[:n]
    ]


def resolve_selection_fn(
    params: MultiXtalSelection,
) -> Callable[[Sequence[XRayCentreResult]], Sequence[XRayCentreResult]]:
    match params:
        case TopNByMaxCountSelection():
            return partial(top_n_by_max_count, n=params.n)
        case TopNByMaxCountForEachSampleSelection():
            return partial(top_n_by_max_count_for_each_sample, n=params.n)
    raise ValueError(f"Invalid selection function {params.name}")


def samples_and_locations_to_collect(
    selection_params: MultiXtalSelection,
    gonio: Smargon,
    default_sample_id: int,
    xrc_results: Sequence[flyscan_result.XRayCentreResult] | None,
) -> MsgGenerator[list[tuple[int, np.ndarray]]]:
    """
    Determine the sample IDs and positions to collect given the specified selection parameters.
    If no centres are present, return the default sample ID and current position,
    so that a collection can be performed without XRC should this be required.
    """
    if xrc_results:
        selection_func = resolve_selection_fn(selection_params)
        hits = selection_func(xrc_results)
        hits_to_collect = []
        for hit in hits:
            if hit.sample_id is None:
                LOGGER.warning(
                    f"Diffracting centre {hit} not collected because no sample id was assigned."
                )
            else:
                hits_to_collect.append(hit)

        samples_and_locations = [
            (hit.sample_id, hit.centre_of_mass_mm * 1000) for hit in hits_to_collect
        ]
        LOGGER.info(
            f"Selected hits {hits_to_collect} using {selection_func}, args={selection_params}"
        )
        return samples_and_locations
    else:
        # If the xray centring hasn't found a result but has not thrown an error it
        # means that we do not need to recentre and can collect where we are
        initial_x_mm = yield from bps.rd(gonio.x.user_readback)
        initial_y_mm = yield from bps.rd(gonio.y.user_readback)
        initial_z_mm = yield from bps.rd(gonio.z.user_readback)

        return [
            (
                default_sample_id,
                np.array([initial_x_mm, initial_y_mm, initial_z_mm]) * 1000,
            )
        ]
