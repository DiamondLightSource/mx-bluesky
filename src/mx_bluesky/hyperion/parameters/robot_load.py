from pydantic import Field

from mx_bluesky.common.parameters.components import (
    MxBlueskyParameters,
    WithOptionalEnergyChange,
    WithSample,
    WithSnapshot,
    WithVisit,
)
from mx_bluesky.hyperion.parameters.constants import CONST


class RobotLoadAndEnergyChange(
    MxBlueskyParameters, WithSample, WithSnapshot, WithOptionalEnergyChange, WithVisit
):
    thawing_time: float = Field(default=CONST.I03.THAWING_TIME)
