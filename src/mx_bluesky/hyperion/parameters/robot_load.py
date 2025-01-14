from pydantic import Field

from mx_bluesky.common.parameters.constants import HardwareConstants
from mx_bluesky.common.parameters.robot_load import (
    RobotLoadAndEnergyChange,
    RobotLoadThenCentre,
)
from mx_bluesky.hyperion.parameters.components import WithHyperionUDCFeatures
from mx_bluesky.hyperion.parameters.gridscan import HyperionPinTipCentreThenXrayCentre


class HyperionRobotLoadThenCentre(RobotLoadThenCentre, WithHyperionUDCFeatures):
    thawing_time: float = Field(default=HardwareConstants.THAWING_TIME)
    tip_offset_um: float = Field(default=HardwareConstants.TIP_OFFSET_UM)

    def robot_load_params(self):
        my_params = self.model_dump()
        return RobotLoadAndEnergyChange(**my_params)

    def pin_centre_then_xray_centre_params(self):
        my_params = self.model_dump()
        del my_params["thawing_time"]
        return HyperionPinTipCentreThenXrayCentre(**my_params)
