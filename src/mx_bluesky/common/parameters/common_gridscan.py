from __future__ import annotations

from mx_bluesky.common.parameters.gridscan import (
    GridCommon,
)


class OddYStepsException(Exception): ...


class PinTipCentreThenXrayCentre(GridCommon):
    tip_offset_um: float = 0


class GridScanWithEdgeDetect(GridCommon):
    pass
