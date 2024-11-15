from pydantic import Field

from mx_bluesky.common.parameters.components import (
    MxBlueskyParameters,
    WithOptionalEnergyChange,
    WithSample,
    WithSnapshot,
    WithVisit,
)
from mx_bluesky.common.parameters.constants import HardwareConstants


class RobotLoadAndEnergyChange(
    MxBlueskyParameters, WithSample, WithSnapshot, WithOptionalEnergyChange, WithVisit
):
    thawing_time: float = Field(default=HardwareConstants.THAWING_TIME)
