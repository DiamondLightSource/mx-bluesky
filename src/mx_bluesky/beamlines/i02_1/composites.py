from pathlib import Path

from mx_bluesky.beamlines.i02_1.parameters.gridscan import SpecifiedTwoDGridScan


class I02_1FgsParams(SpecifiedTwoDGridScan):  # noqa: N801
    """For VMXm gridscans, GDA currently takes the snapshots and provides bluesky with a path, and
    sends over the grid parameters"""

    path_to_xtal_snapshot: Path
    beam_size_x: float
    beam_size_y: float
    microns_per_pixel_x: float
    microns_per_pixel_y: float
    upper_left_x: int  # position of X,Y for the top left of the grid, in pixels
    upper_left_y: int
