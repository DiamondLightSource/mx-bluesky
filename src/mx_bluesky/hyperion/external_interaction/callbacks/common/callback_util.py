from collections.abc import Callable

from bluesky.callbacks import CallbackBase

from mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback import (
    ZocaloCallback,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanISPyBCallback,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.nexus_callback import (
    GridscanNexusFileCallback,
)
from mx_bluesky.hyperion.external_interaction.callbacks.robot_load.ispyb_callback import (
    RobotLoadISPyBCallback,
)
from mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback import (
    RotationISPyBCallback,
)
from mx_bluesky.hyperion.external_interaction.callbacks.rotation.nexus_callback import (
    RotationNexusFileCallback,
)

CallbacksFactory = Callable[[], tuple[CallbackBase, ...]]


def create_robot_load_and_centre_callbacks() -> (
    tuple[GridscanNexusFileCallback, GridscanISPyBCallback, RobotLoadISPyBCallback]
):
    return (
        GridscanNexusFileCallback(),
        GridscanISPyBCallback(emit=ZocaloCallback()),
        RobotLoadISPyBCallback(),
    )


def create_gridscan_callbacks() -> (
    tuple[GridscanNexusFileCallback, GridscanISPyBCallback]
):
    return (GridscanNexusFileCallback(), GridscanISPyBCallback(emit=ZocaloCallback()))


def create_rotation_callbacks() -> (
    tuple[RotationNexusFileCallback, RotationISPyBCallback]
):
    return (RotationNexusFileCallback(), RotationISPyBCallback(emit=ZocaloCallback()))


def create_load_centre_collect_callbacks() -> (
    tuple[
        GridscanNexusFileCallback,
        GridscanISPyBCallback,
        RobotLoadISPyBCallback,
        RotationNexusFileCallback,
        RotationISPyBCallback,
    ]
):
    return (
        GridscanNexusFileCallback(),
        GridscanISPyBCallback(emit=ZocaloCallback()),
        RobotLoadISPyBCallback(),
        RotationNexusFileCallback(),
        RotationISPyBCallback(emit=ZocaloCallback()),
    )
