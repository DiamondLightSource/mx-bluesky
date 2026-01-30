from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from functools import partial

from mx_bluesky.common.xrc_result import XRayCentreResult
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
