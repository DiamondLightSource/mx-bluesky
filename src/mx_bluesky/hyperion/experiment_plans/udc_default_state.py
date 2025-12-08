import bluesky.plan_stubs as bps
import pydantic
from bluesky.utils import MsgGenerator
from dodal.common.beamlines.beamline_parameters import (
    get_beamline_parameters,
)
from dodal.devices.aperturescatterguard import ApertureValue
from dodal.devices.collimation_table import CollimationTable
from dodal.devices.cryostream import (
    CryoStreamGantry,
    CryoStreamSelection,
    OxfordCryoJet,
    OxfordCryoStream,
)
from dodal.devices.cryostream import InOut as CryoInOut
from dodal.devices.fluorescence_detector_motion import FluorescenceDetector
from dodal.devices.fluorescence_detector_motion import InOut as FlouInOut
from dodal.devices.hutch_shutter import HutchShutter, ShutterDemand
from dodal.devices.mx_phase1.beamstop import BeamstopPositions
from dodal.devices.robot import BartRobot, PinMounted
from dodal.devices.scintillator import InOut as ScinInOut
from dodal.devices.scintillator import Scintillator
from dodal.devices.smargon import Smargon
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutterState

from mx_bluesky.common.experiment_plans.beamstop_check import (
    BeamstopCheckDevices,
    move_beamstop_in_and_verify_using_diode,
)
from mx_bluesky.common.utils.exceptions import BeamlineCheckFailureError
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.external_interaction.config_server import (
    get_hyperion_config_client,
)
from mx_bluesky.hyperion.parameters.constants import CONST, HyperionFeatureSettings

_GROUP_PRE_BEAMSTOP_CHECK = "pre_beamstop_check"
_GROUP_POST_BEAMSTOP_CHECK = "post_beamstop_check"


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class UDCDefaultDevices(BeamstopCheckDevices):
    collimation_table: CollimationTable
    cryojet: OxfordCryoJet
    cryostream: OxfordCryoStream
    cryostream_gantry: CryoStreamGantry
    fluorescence_det_motion: FluorescenceDetector
    hutch_shutter: HutchShutter
    robot: BartRobot
    scintillator: Scintillator
    smargon: Smargon


class UnexpectedSampleError(BeamlineCheckFailureError): ...


class CryoStreamError(BeamlineCheckFailureError): ...


def move_to_udc_default_state(devices: UDCDefaultDevices):
    """Moves beamline to known positions prior to UDC start"""
    yield from _verify_correct_cryostream_selected(devices.cryostream_gantry)

    cryostream_temp = yield from bps.rd(devices.cryostream.temp)
    cryostream_pressure = yield from bps.rd(devices.cryostream.back_pressure)
    if cryostream_temp > CONST.HARDWARE.MAX_CRYO_TEMP_K:
        raise CryoStreamError("Cryostream temperature is too high, not starting UDC")
    if cryostream_pressure > CONST.HARDWARE.MAX_CRYO_PRESSURE_BAR:
        raise CryoStreamError("Cryostream back pressure is too high, not starting UDC")

    yield from _verify_no_sample_present(devices.robot)

    # Close fast shutter before opening hutch shutter
    yield from bps.abs_set(devices.sample_shutter, ZebraShutterState.CLOSE, wait=True)

    commissioning_mode_enabled = yield from bps.rd(devices.baton.commissioning)

    if commissioning_mode_enabled:
        LOGGER.warning("Not opening hutch shutter - commissioning mode is enabled.")
    else:
        yield from bps.abs_set(
            devices.hutch_shutter, ShutterDemand.OPEN, group=_GROUP_PRE_BEAMSTOP_CHECK
        )

    yield from bps.abs_set(devices.scintillator.selected_pos, ScinInOut.OUT, wait=True)

    yield from bps.abs_set(
        devices.fluorescence_det_motion.pos,
        FlouInOut.OUT,
        group=_GROUP_PRE_BEAMSTOP_CHECK,
    )

    yield from bps.abs_set(
        devices.collimation_table.inboard_y,
        0,
        group=_GROUP_PRE_BEAMSTOP_CHECK,
    )
    yield from bps.abs_set(
        devices.collimation_table.outboard_y, 0, group=_GROUP_PRE_BEAMSTOP_CHECK
    )
    yield from bps.abs_set(
        devices.collimation_table.upstream_y, 0, group=_GROUP_PRE_BEAMSTOP_CHECK
    )
    yield from bps.abs_set(
        devices.collimation_table.upstream_x, 0, group=_GROUP_PRE_BEAMSTOP_CHECK
    )
    yield from bps.abs_set(
        devices.collimation_table.downstream_x, 0, group=_GROUP_PRE_BEAMSTOP_CHECK
    )

    # Wait for all of the above to complete
    yield from bps.wait(group=_GROUP_PRE_BEAMSTOP_CHECK, timeout=0.1)

    feature_flags: HyperionFeatureSettings = (
        get_hyperion_config_client().get_feature_flags()
    )
    if feature_flags.BEAMSTOP_DIODE_CHECK:
        beamline_parameters = get_beamline_parameters()
        config_client = get_hyperion_config_client()
        features_settings: HyperionFeatureSettings = config_client.get_feature_flags()
        detector_min_z = features_settings.DETECTOR_DISTANCE_LIMIT_MIN_MM
        detector_max_z = features_settings.DETECTOR_DISTANCE_LIMIT_MAX_MM
        yield from move_beamstop_in_and_verify_using_diode(
            devices, beamline_parameters, detector_min_z, detector_max_z
        )
    else:
        yield from bps.abs_set(
            devices.beamstop.selected_pos, BeamstopPositions.DATA_COLLECTION, wait=True
        )

    yield from bps.abs_set(
        devices.aperture_scatterguard.selected_aperture,
        ApertureValue.SMALL,
        group=_GROUP_POST_BEAMSTOP_CHECK,
    )

    yield from bps.abs_set(
        devices.cryojet.coarse, CryoInOut.IN, group=_GROUP_POST_BEAMSTOP_CHECK
    )
    yield from bps.abs_set(
        devices.cryojet.fine, CryoInOut.IN, group=_GROUP_POST_BEAMSTOP_CHECK
    )

    yield from bps.wait(_GROUP_POST_BEAMSTOP_CHECK)


def _verify_correct_cryostream_selected(
    cryostream_gantry: CryoStreamGantry,
) -> MsgGenerator:
    cryostream_selection = yield from bps.rd(cryostream_gantry.cryostream_selector)
    cryostream_selected = yield from bps.rd(cryostream_gantry.cryostream_selected)
    if cryostream_selection != CryoStreamSelection.CRYOJET or cryostream_selected != 1:
        raise CryoStreamError(
            f"Cryostream is not selected for use, control PV selection = {cryostream_selection}, "
            f"current status {cryostream_selected}"
        )


def _verify_no_sample_present(robot: BartRobot):
    pin_mounted = yield from bps.rd(robot.gonio_pin_sensor)

    if pin_mounted != PinMounted.NO_PIN_MOUNTED:
        # Cannot unload this sample because we do not know the correct visit for it
        raise UnexpectedSampleError(
            "An unexpected sample was found, please unload the sample manually."
        )
