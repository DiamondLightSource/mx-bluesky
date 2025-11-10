import bluesky.plan_stubs as bps
import pydantic
from bluesky.utils import MsgGenerator
from dodal.common.beamlines.beamline_parameters import (
    GDABeamlineParameters,
    get_beamline_parameters,
)
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.baton import Baton
from dodal.devices.collimation_table import CollimationTable
from dodal.devices.cryostream import CryoStream, CryoStreamGantry, CryoStreamSelection
from dodal.devices.cryostream import InOut as CryoInOut
from dodal.devices.detector.detector_motion import DetectorMotion, ShutterState
from dodal.devices.fluorescence_detector_motion import (
    FluorescenceDetector,
)
from dodal.devices.fluorescence_detector_motion import InOut as FlouInOut
from dodal.devices.hutch_shutter import HutchShutter, ShutterDemand
from dodal.devices.ipin import IPin, IPinGain
from dodal.devices.mx_phase1.beamstop import Beamstop, BeamstopPositions
from dodal.devices.robot import BartRobot, PinMounted
from dodal.devices.scintillator import InOut as ScinInOut
from dodal.devices.scintillator import Scintillator
from dodal.devices.smargon import Smargon
from dodal.devices.tetramm import BasicTetrammDetector
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter, ZebraShutterState
from ophyd_async.core import InOut

from mx_bluesky.common.device_setup_plans.xbpm_feedback import (
    unpause_xbpm_feedback_and_set_transmission_to_1,
)
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.external_interaction.config_server import (
    get_hyperion_config_client,
)
from mx_bluesky.hyperion.parameters.constants import HyperionFeatureSetting

_GROUP_PRE_BEAMSTOP_OUT_CHECK = "pre_background_check"
_GROUP_POST_BEAMSTOP_OUT_CHECK = "post_background_check"
_GROUP_PRE_BEAMSTOP_CHECK = "pre_beamstop_check"
_GROUP_POST_BEAMSTOP_CHECK = "post_beamstop_check"

_PARAM_DATA_COLLECTION_MIN_SAMPLE_CURRENT = "dataCollectionMinSampleCurrent"
_PARAM_IPIN_THRESHOLD = "ipin_threshold"

_FEEDBACK_TIMEOUT_S = 10


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class UDCDefaultDevices:
    aperture_scatterguard: ApertureScatterguard
    attenuator: BinaryFilterAttenuator
    backlight: Backlight
    baton: Baton
    beamstop: Beamstop
    collimation_table: CollimationTable
    hutch_shutter: HutchShutter
    cryostream: CryoStream
    cryostream_gantry: CryoStreamGantry
    detector_motion: DetectorMotion
    fluorescence_det_motion: FluorescenceDetector
    hutch_shutter: HutchShutter
    ipin: IPin
    robot: BartRobot
    sample_shutter: ZebraShutter
    scintillator: Scintillator
    smargon: Smargon
    xbpm_feedback: XBPMFeedback
    xbpm1: BasicTetrammDetector


class DefaultStateCheckFailureError(RuntimeError): ...

class SampleCurrentBelowThresholdError(DefaultStateCheckFailureError): ...


class BeamObstructedError(DefaultStateCheckFailureError): ...


class BeamstopNotInPositionError(DefaultStateCheckFailureError): ...


class UnexpectedSampleError(DefaultStateCheckFailureError): ...


class CryostreamError(DefaultStateCheckFailureError): ...


def move_to_udc_default_state(devices: UDCDefaultDevices):
    """Moves beamline to known positions prior to UDC start"""
    yield from _verify_correct_cryostream_selected(devices.cryostream_gantry)

    cryostream_temp = yield from bps.rd(devices.cryostream.temperature_k)
    cryostream_pressure = yield from bps.rd(devices.cryostream.back_pressure_bar)
    if cryostream_temp > devices.cryostream.MAX_TEMP_K:
        raise CryostreamError("Cryostream temperature is too high, not starting UDC")
    if cryostream_pressure > devices.cryostream.MAX_PRESSURE_BAR:
        raise CryostreamError("Cryostream back pressure is too high, not starting UDC")

    yield from bps.abs_set(
        devices.hutch_shutter, ShutterDemand.OPEN, group="udc_default"
    )


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
    yield from bps.wait(group=_GROUP_PRE_BEAMSTOP_CHECK)

    beamline_parameters = get_beamline_parameters()
    yield from move_beamstop_in_and_verify_using_diode(devices, beamline_parameters)

    yield from bps.abs_set(
        devices.aperture_scatterguard.selected_aperture,
        ApertureValue.SMALL,
        group=_GROUP_POST_BEAMSTOP_CHECK,
    )

    yield from bps.abs_set(
        devices.cryostream.course, CryoInOut.IN, group=_GROUP_POST_BEAMSTOP_CHECK
    )
    yield from bps.abs_set(
        devices.cryostream.fine, CryoInOut.IN, group=_GROUP_POST_BEAMSTOP_CHECK
    )

    yield from bps.wait(_GROUP_POST_BEAMSTOP_CHECK)


def move_beamstop_in_and_verify_using_diode(
    devices: UDCDefaultDevices, beamline_parameters: GDABeamlineParameters
) -> MsgGenerator:
    """
    Move the beamstop into the data collection position, comparing before and after the beam
    current via the diode on the detector shutter, in order to verify that the beamstop has
    been successfully moved.

    As a side-effect, also does the following things:
        * Move the detector z-axis in range
        * Move the backlight out
        * Unpauses feedback
        * Sets xmission to 100%
        * Sets IPin gain to 10^4 low noise
        * Moves aperture scatterguard to OUT_OF_BEAM if it is currently in beam

    Implementation note:
        Some checks are repeated here such as closing the sample shutter, so that at a
        future point this plan may be run independently of the udc default state script
        if desired.
    Note on commissioning mode:
        When commissioning mode is enabled, normally the beamstop check will execute albeit
        where it expects beam to be present, the absence of beam will be ignored.
    Args:
        devices: The device composite containing the necessary devices
        beamline_parameters: A mapping containing the beamlineParameters
    Raises:
        SampleCurrentBelowThresholdError: If we do not have sufficient sample current to perform
            the check.
        BeamstopNotInPositionError: If the ipin current is too high, indicating that the
            beamstop is not in the correct position.
    """
    LOGGER.info("Performing beamstop check...")
    commissioning_mode_enabled = yield from bps.rd(devices.baton.commissioning)

    # Re-verify that the sample shutter is closed
    yield from bps.abs_set(devices.sample_shutter, ZebraShutterState.CLOSE, wait=True)
    # xbpm1 > 1e-8
    LOGGER.info("Unpausing feedback, transmission to 100%, wait for feedback stable...")
    # if commissioning_mode_enabled:
        # LOGGER.warning("Not waiting for feedback - commissioning mode is enabled.")
    try:
        yield from unpause_xbpm_feedback_and_set_transmission_to_1(
            devices.xbpm_feedback,
            devices.attenuator,
            0 if commissioning_mode_enabled else _FEEDBACK_TIMEOUT_S,
        )
    except TimeoutError as e:
        raise SampleCurrentBelowThresholdError(
            "Unable to perform beamstop check - xbpm feedback did not become stable "
            " - check if beam present?"
        ) from e

    yield from bps.abs_set(
        devices.backlight, InOut.OUT, group=_GROUP_PRE_BEAMSTOP_OUT_CHECK
    )

    config_client = get_hyperion_config_client()
    detector_current_z = yield from bps.rd(devices.detector_motion.z)
    features_settings: HyperionFeatureSetting = config_client.get_feature_flags()
    detector_min_z = features_settings.DETECTOR_DISTANCE_LIMIT_MIN_MM
    detector_max_z = features_settings.DETECTOR_DISTANCE_LIMIT_MAX_MM
    target_z = max(min(detector_current_z, detector_max_z), detector_min_z)
    if detector_current_z != target_z:
        LOGGER.info(
            f"Detector distance {detector_current_z}mm outside acceptable range {detector_min_z} <= z <="
            f" {detector_max_z}, moving it."
        )
        yield from bps.abs_set(
            devices.detector_motion.z, target_z, group=_GROUP_POST_BEAMSTOP_OUT_CHECK
        )

    yield from bps.trigger(
        devices.xbpm_feedback, group=_GROUP_PRE_BEAMSTOP_OUT_CHECK, wait=True
    )

    yield from _beamstop_check_actions_with_sample_out(devices, beamline_parameters)


def _verify_correct_cryostream_selected(
    cryostream_gantry: CryoStreamGantry,
) -> MsgGenerator:
    cryostream_selection = yield from bps.rd(cryostream_gantry.cryostream_selector)
    cryostream_selected = yield from bps.rd(cryostream_gantry.cryostream_selected)
    if cryostream_selection != CryoStreamSelection.CRYOJET or cryostream_selected != 1:
        raise CryostreamError(
            f"Cryostream is not selected for use, control PV selection = {cryostream_selection}, "
            f"current status {cryostream_selected}"
        )


def _verify_no_sample_present(robot: BartRobot):
    sample_id = yield from bps.rd(robot.sample_id)
    pin_mounted = yield from bps.rd(robot.gonio_pin_sensor)

    if sample_id or pin_mounted != PinMounted.NO_PIN_MOUNTED:
        # Cannot unload this sample because we do not know the correct visit for it
        raise UnexpectedSampleError(
            "An unexpected sample was found, please unload the sample manually."
        )


def _beamstop_check_actions_with_sample_out(
    devices: UDCDefaultDevices, beamline_parameters: GDABeamlineParameters
) -> MsgGenerator:
    commissioning_mode_enabled = yield from bps.rd(devices.baton.commissioning)

    yield from bps.abs_set(
        devices.aperture_scatterguard.selected_aperture,
        ApertureValue.OUT_OF_BEAM,
        group=_GROUP_PRE_BEAMSTOP_OUT_CHECK,
    )

    yield from bps.abs_set(
        devices.ipin.gain,
        IPinGain.GAIN_10E4_LOW_NOISE,
        group=_GROUP_PRE_BEAMSTOP_OUT_CHECK,
    )
    yield from bps.abs_set(
        devices.detector_motion.shutter,
        ShutterState.CLOSED,
        group=_GROUP_PRE_BEAMSTOP_OUT_CHECK,
    )
    yield from bps.abs_set(
        devices.beamstop.selected_pos,
        BeamstopPositions.OUT,
        group=_GROUP_PRE_BEAMSTOP_OUT_CHECK,
    )

    LOGGER.info("Waiting for pre-background-check motions to complete...")
    yield from bps.wait(group=_GROUP_PRE_BEAMSTOP_OUT_CHECK)

    # Check sample shutter is closed and detector shutter is closed
    shutter_ = yield from bps.rd(devices.sample_shutter)
    sample_shutter_is_closed = (shutter_) == ZebraShutterState.CLOSE
    motion_shutter_ = yield from bps.rd(devices.detector_motion.shutter)
    detector_shutter_is_closed = (motion_shutter_) == ShutterState.CLOSED
    if not (sample_shutter_is_closed and detector_shutter_is_closed):
        raise RuntimeError(
            "Unable to proceed with beamstop background check, shutters did not close"
        )

    # raise DefaultStateCheckFailureError("Reached planned stop point for testing.")

    yield from bps.abs_set(devices.sample_shutter, ZebraShutterState.OPEN, wait=True)
    yield from bps.sleep(1)  # wait for reading to settle

    ipin_beamstop_out_uA = yield from bps.rd(devices.ipin.pin_readback)  # noqa: N806
    yield from bps.abs_set(devices.sample_shutter, ZebraShutterState.CLOSE, wait=True)
    LOGGER.info(f"Beamstop out ipin = {ipin_beamstop_out_uA}uA")

    beamstop_threshold_uA = beamline_parameters[_PARAM_IPIN_THRESHOLD]  # noqa: N806
    if ipin_beamstop_out_uA < beamstop_threshold_uA:
        msg = (
            f"IPin current {ipin_beamstop_out_uA}uA below threshold "
            f"{beamstop_threshold_uA} with beamstop out - check "
            f"that beam is not obstructed."
        )
        if commissioning_mode_enabled:
            LOGGER.warning(msg + " - commissioning mode enabled - ignoring this")
        else:
            raise BeamObstructedError(msg)

    yield from bps.abs_set(
        devices.beamstop.selected_pos,
        BeamstopPositions.DATA_COLLECTION,
        group=_GROUP_POST_BEAMSTOP_OUT_CHECK,
    )

    LOGGER.info("Waiting for detector motion to complete...")
    yield from bps.wait(group=_GROUP_POST_BEAMSTOP_OUT_CHECK)

    LOGGER.info("Opening sample shutter...")
    yield from bps.abs_set(devices.sample_shutter, ZebraShutterState.OPEN, wait=True)

    yield from bps.sleep(1)  # wait for reading to settle
    ipin_in_beam_uA = yield from bps.rd(devices.ipin.pin_readback)  # noqa: N806

    yield from bps.abs_set(devices.sample_shutter, ZebraShutterState.CLOSE, wait=True)
    if ipin_in_beam_uA > beamstop_threshold_uA:
        raise BeamstopNotInPositionError(
            f"Ipin is too high at {ipin_in_beam_uA} - check that beamstop is "
            f"in the correct position."
        )
