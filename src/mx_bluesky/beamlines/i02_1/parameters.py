from pathlib import Path

from dodal.devices.aperturescatterguard import ApertureValue
from pydantic import Field

from mx_bluesky.common.parameters.components import (
    DiffractionExperimentWithSample,
    IspybExperimentType,
)
from mx_bluesky.common.parameters.constants import GridscanParamConstants


class I02_1FgsParams(DiffractionExperimentWithSample):  # noqa: N801
    """For VMXm gridscans, GDA currently takes the snapshots and provides bluesky with a path, and
    sends over the grid parameters"""

    path_to_xtal_snapshot: Path
    beam_size_x: float
    beam_size_y: float
    microns_per_pixel_x: float
    microns_per_pixel_y: float
    upper_left_x: int  # position of X,Y for the top left of the grid, in pixels
    upper_left_y: int

    # Overrides of default values in the superclass
    exposure_time_s: float = Field(default=GridscanParamConstants.EXPOSURE_TIME_S)
    ispyb_experiment_type: IspybExperimentType = Field(
        default=IspybExperimentType.GRIDSCAN_3D
    )
    selected_aperture: ApertureValue | None = Field(default=ApertureValue.SMALL)
