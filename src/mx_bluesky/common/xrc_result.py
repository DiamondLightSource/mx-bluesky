from __future__ import annotations

import dataclasses
from collections import defaultdict
from collections.abc import Callable, Sequence
from functools import partial

import numpy as np
from bluesky.callbacks import CallbackBase
from event_model import RunStart

from mx_bluesky.common.parameters.components import (
    MultiXtalSelection,
    TopNByMaxCountForEachSampleSelection,
    TopNByMaxCountSelection,
)


class XRayCentreEventHandler(CallbackBase):
    def __init__(self):
        super().__init__()
        self.xray_centre_results: Sequence[XRayCentreResult] | None = None

    def start(self, doc: RunStart) -> RunStart | None:
        if "xray_centre_results" in doc:
            self.xray_centre_results = [
                XRayCentreResult(**result_dict)
                for result_dict in doc["xray_centre_results"]  # type: ignore
            ]
        return doc


@dataclasses.dataclass
class XRayCentreResult:
    """
    Represents information about a hit from an X-ray centring.

    Attributes:
        centre_of_mass_mm: coordinates in mm of the centre of mass
        bounding_box_mm: coordinates in mm of opposite corners of the bounding box
            containing the crystal
        max_count: The maximum spot count encountered in any one grid box in the crystal
        total_count: The total count across all boxes in the crystal.
        sample_id: The sample id associated with the centre.
    """

    centre_of_mass_mm: np.ndarray
    bounding_box_mm: tuple[np.ndarray, np.ndarray]
    max_count: int
    total_count: int
    sample_id: int | None

    def __eq__(self, o):
        return (
            isinstance(o, XRayCentreResult)
            and o.max_count == self.max_count
            and o.total_count == self.total_count
            and o.sample_id == self.sample_id
            and all(o.centre_of_mass_mm == self.centre_of_mass_mm)
            and all(o.bounding_box_mm[0] == self.bounding_box_mm[0])
            and all(o.bounding_box_mm[1] == self.bounding_box_mm[1])
        )


def top_n_by_max_count(
    unfiltered: Sequence[XRayCentreResult], n: int
) -> Sequence[XRayCentreResult]:
    sorted_hits = sorted(unfiltered, key=lambda result: result.max_count, reverse=True)
    return sorted_hits[:n]


def top_n_by_max_count_for_each_sample(
    unfiltered: Sequence[XRayCentreResult], n: int
) -> Sequence[XRayCentreResult]:
    xrc_results_by_sample_id: dict[int, list[XRayCentreResult]] = defaultdict(
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
