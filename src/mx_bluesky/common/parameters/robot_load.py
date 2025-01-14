from pydantic import Field

from mx_bluesky.common.parameters.components import (
    MxBlueskyParameters,
    WithOptionalEnergyChange,
    WithSample,
    WithSnapshot,
    WithVisit,
)
from mx_bluesky.common.parameters.constants import HardwareConstants
from mx_bluesky.common.parameters.gridscan import GridCommon, PinTipCentreThenXrayCentre


class RobotLoadAndEnergyChange(
    MxBlueskyParameters, WithSample, WithSnapshot, WithOptionalEnergyChange, WithVisit
):
    thawing_time: float = Field(default=HardwareConstants.THAWING_TIME)


class RobotLoadThenCentre(GridCommon):
    thawing_time: float = Field(default=HardwareConstants.THAWING_TIME)

    def robot_load_params(self):
        my_params = self.model_dump()
        return RobotLoadAndEnergyChange(**my_params)

    def pin_centre_then_xray_centre_params(self):
        my_params = self.model_dump()
        del my_params["thawing_time"]
        return PinTipCentreThenXrayCentre(**my_params)
