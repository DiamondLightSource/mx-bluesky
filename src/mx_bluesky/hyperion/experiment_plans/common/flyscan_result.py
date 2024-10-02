from __future__ import annotations

import dataclasses
from collections.abc import Sequence

import numpy as np


@dataclasses.dataclass
class FlyscanResult:
    """Represents information about a hit from a flyscan."""

    centre_of_mass_mm: np.ndarray
    bounding_box_mm: tuple[np.ndarray, np.ndarray]
    max_count: int
    total_count: int

    def __eq__(self, o):
        return (
            isinstance(o, FlyscanResult)
            and o.max_count == self.max_count
            and o.total_count == self.total_count
            and all(o.centre_of_mass_mm == self.centre_of_mass_mm)
            and all(o.bounding_box_mm[0] == self.bounding_box_mm[0])
            and all(o.bounding_box_mm[1] == self.bounding_box_mm[1])
        )


def top_n_by_max_count(
    unfiltered: Sequence[FlyscanResult], n: int
) -> Sequence[FlyscanResult]:
    sorted_hits = sorted(unfiltered, key=lambda result: result.max_count, reverse=True)
    return sorted_hits[:n]
