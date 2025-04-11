from mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback import (
    ZocaloCallback,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.nexus_callback import (
    GridscanNexusFileCallback,
)
from mx_bluesky.common.parameters.constants import (
    EnvironmentConstants,
    PlanNameConstants,
)
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan


def create_gridscan_callbacks() -> tuple[
    GridscanNexusFileCallback, GridscanISPyBCallback
]:
    return (
        GridscanNexusFileCallback(param_type=SpecifiedThreeDGridScan),
        GridscanISPyBCallback(
            param_type=SpecifiedThreeDGridScan,
            emit=ZocaloCallback(
                PlanNameConstants.DO_FGS, EnvironmentConstants.ZOCALO_ENV
            ),
        ),
    )
