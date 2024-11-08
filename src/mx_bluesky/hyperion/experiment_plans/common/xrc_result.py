from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from functools import partial

import numpy as np

from mx_bluesky.common.parameters.components import (
    MultiXtalSelection,
    TopNByMaxCountSelection,
)


@dataclasses.dataclass
class XRayCentreResult:
    """Represents information about a hit from an X-ray centring."""

    centre_of_mass_mm: np.ndarray
    bounding_box_mm: tuple[np.ndarray, np.ndarray]
    max_count: int
    total_count: int

    def __eq__(self, o):
        return (
            isinstance(o, XRayCentreResult)
            and o.max_count == self.max_count
            and o.total_count == self.total_count
            and all(o.centre_of_mass_mm == self.centre_of_mass_mm)
            and all(o.bounding_box_mm[0] == self.bounding_box_mm[0])
            and all(o.bounding_box_mm[1] == self.bounding_box_mm[1])
        )


def top_n_by_max_count(
    unfiltered: Sequence[XRayCentreResult], n: int
) -> Sequence[XRayCentreResult]:
    sorted_hits = sorted(unfiltered, key=lambda result: result.max_count, reverse=True)
    return sorted_hits[:n]


def resolve_selection_fn(
    params: MultiXtalSelection,
) -> Callable[[Sequence[XRayCentreResult]], Sequence[XRayCentreResult]]:
    if isinstance(params, TopNByMaxCountSelection):
        return partial(top_n_by_max_count, n=params.n)
    raise ValueError(f"Invalid selection function {params.name}")
