from bluesky.callbacks import CallbackBase
from event_model import Event

from mx_bluesky.beamlines.phase1.beamsize.phase1_aperture_scatterguard import (
    map_hw_read_during_data,
)
from mx_bluesky.common.device_setup_plans.detector.eiger import (
    eiger_hw_read_during_mapper,
    eiger_zocalo_hw_read_mapper,
)
from mx_bluesky.common.external_interaction.callbacks.common.log_uid_tag_callback import (
    LogUidTaggingCallback,
)
from mx_bluesky.common.external_interaction.callbacks.common.zocalo_callback import (
    ZocaloCallback,
)
from mx_bluesky.common.external_interaction.callbacks.grid.grid_detect_and_scan.event_mapping import (
    HWReadDuringPayload,
)
from mx_bluesky.common.external_interaction.callbacks.grid.grid_detect_and_scan.ispyb_callback import (
    GridDetectAndScanISPyBCallback,
)
from mx_bluesky.common.external_interaction.callbacks.grid.grid_detect_and_scan.nexus_callback import (
    GridscanNexusFileCallback,
)
from mx_bluesky.common.external_interaction.callbacks.grid.utils import (
    generate_start_info_from_omega_map,
)
from mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback import (
    SampleHandlingCallback,
)
from mx_bluesky.common.parameters.constants import GridscanParamConstants
from mx_bluesky.hyperion.external_interaction.callbacks.alert_on_container_change import (
    AlertOnContainerChange,
)
from mx_bluesky.hyperion.external_interaction.callbacks.robot_actions.ispyb_callback import (
    RobotLoadISPyBCallback,
)
from mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback import (
    RotationISPyBCallback,
    generate_start_info_from_ordered_runs,
)
from mx_bluesky.hyperion.external_interaction.callbacks.rotation.nexus_callback import (
    RotationNexusFileCallback,
)
from mx_bluesky.hyperion.external_interaction.callbacks.snapshot_callback import (
    BeamDrawingCallback,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.robot_load import RobotLoadThenCentre


def setup_callbacks() -> list[CallbackBase]:
    rot_nexus_cb, rot_ispyb_cb = _create_rotation_callbacks()
    snapshot_cb = BeamDrawingCallback(emit=rot_ispyb_cb)
    return [
        *_create_gridscan_callbacks(),
        rot_nexus_cb,
        snapshot_cb,
        LogUidTaggingCallback(),
        RobotLoadISPyBCallback(),
        SampleHandlingCallback(),
        AlertOnContainerChange(),
    ]


def _create_gridscan_callbacks() -> tuple[
    GridscanNexusFileCallback, GridDetectAndScanISPyBCallback
]:
    return (
        GridscanNexusFileCallback(
            param_type=RobotLoadThenCentre, hw_read_mapper=_hw_read_during_mapper
        ),
        GridDetectAndScanISPyBCallback(
            param_type=RobotLoadThenCentre,
            emit=ZocaloCallback(
                CONST.PLAN.DO_FGS,
                CONST.ZOCALO_ENV,
                lambda: generate_start_info_from_omega_map(
                    [GridscanParamConstants.OMEGA_1, GridscanParamConstants.OMEGA_2]
                ),
                eiger_zocalo_hw_read_mapper,
            ),
            hw_read_during_mapper=_hw_read_during_mapper,
        ),
    )


def _create_rotation_callbacks() -> tuple[
    RotationNexusFileCallback, RotationISPyBCallback
]:
    return (
        RotationNexusFileCallback(),
        RotationISPyBCallback(
            emit=ZocaloCallback(
                CONST.PLAN.ROTATION_MULTI,
                CONST.ZOCALO_ENV,
                generate_start_info_from_ordered_runs,
                eiger_zocalo_hw_read_mapper,
            ),
            hw_read_during_mapper=_hw_read_during_mapper,
        ),
    )


def _hw_read_during_mapper(doc: Event) -> HWReadDuringPayload:
    detector_payload = eiger_hw_read_during_mapper(doc)
    beamsize_payload = map_hw_read_during_data(doc)
    return HWReadDuringPayload(
        detector_payload=detector_payload, beamsize_payload=beamsize_payload
    )
