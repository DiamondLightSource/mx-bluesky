import pydantic
from bluesky import plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common.beamlines.beamline_parameters import GDABeamlineParameters
from dodal.devices.aperturescatterguard import ApertureScatterguard, ApertureValue
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.baton import Baton
from dodal.devices.detector.detector_motion import DetectorMotion, ShutterState
from dodal.devices.ipin import IPin, IPinGain
from dodal.devices.mx_phase1.beamstop import Beamstop, BeamstopPositions
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra_controlled_shutter import ZebraShutter, ZebraShutterState
from ophyd_async.core import InOut

from mx_bluesky.common.device_setup_plans.xbpm_feedback import (
    unpause_xbpm_feedback_and_set_transmission_to_1,
)
from mx_bluesky.common.utils.exceptions import BeamlineCheckFailureError
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.external_interaction.config_server import (
    get_hyperion_config_client,
)
from mx_bluesky.hyperion.parameters.constants import HyperionFeatureSetting

_GROUP_PRE_BEAMSTOP_OUT_CHECK = "pre_background_check"
_GROUP_POST_BEAMSTOP_OUT_CHECK = "post_background_check"
_PARAM_IPIN_THRESHOLD = "ipin_threshold"

_FEEDBACK_TIMEOUT_S = 10


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class BeamstopCheckDevices:
    aperture_scatterguard: ApertureScatterguard
    attenuator: BinaryFilterAttenuator
    backlight: Backlight
    baton: Baton
    beamstop: Beamstop
    detector_motion: DetectorMotion
    ipin: IPin
    sample_shutter: ZebraShutter
    xbpm_feedback: XBPMFeedback


class SampleCurrentBelowThresholdError(BeamlineCheckFailureError): ...


class BeamstopNotInPositionError(BeamlineCheckFailureError): ...


class BeamObstructedError(BeamlineCheckFailureError): ...


def move_beamstop_in_and_verify_using_diode(
    devices: BeamstopCheckDevices, beamline_parameters: GDABeamlineParameters
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
    beamstop_threshold_uA = beamline_parameters[_PARAM_IPIN_THRESHOLD]  # noqa: N806

    yield from _pre_beamstop_out_check_actions(devices, commissioning_mode_enabled)
    yield from _beamstop_out_check(
        devices, beamstop_threshold_uA, commissioning_mode_enabled
    )
    yield from _post_beamstop_out_check_actions(devices)
    yield from _beamstop_in_check(devices, beamstop_threshold_uA)


def _pre_beamstop_out_check_actions(
    devices: BeamstopCheckDevices, commissioning_mode_enabled: bool
):
    # Re-verify that the sample shutter is closed
    yield from bps.abs_set(devices.sample_shutter, ZebraShutterState.CLOSE, wait=True)
    LOGGER.info("Unpausing feedback, transmission to 100%, wait for feedback stable...")
    if commissioning_mode_enabled:
        # Commissioning mode is checked in the dodal device and xbpm_feedback will be
        # skipped if commissioning mode is on
        LOGGER.warning("Not waiting for feedback - commissioning mode is enabled.")
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

    yield from _start_moving_detector_if_needed(devices)

    yield from bps.abs_set(
        devices.backlight, InOut.OUT, group=_GROUP_PRE_BEAMSTOP_OUT_CHECK
    )

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


def _start_moving_detector_if_needed(devices: BeamstopCheckDevices):
    config_client = get_hyperion_config_client()
    detector_current_z = yield from bps.rd(devices.detector_motion.z)
    features_settings: HyperionFeatureSetting = config_client.get_feature_flags()
    detector_min_z = features_settings.DETECTOR_DISTANCE_LIMIT_MIN_MM
    detector_max_z = features_settings.DETECTOR_DISTANCE_LIMIT_MAX_MM
    target_z = max(min(detector_current_z, detector_max_z), detector_min_z)
    if detector_current_z != target_z:
        LOGGER.info(
            f"Detector distance {detector_current_z}mm outside acceptable range for diode "
            f"check {detector_min_z} <= z <= {detector_max_z}, moving it."
        )
        yield from bps.abs_set(
            devices.detector_motion.z, target_z, group=_GROUP_POST_BEAMSTOP_OUT_CHECK
        )


def _post_beamstop_out_check_actions(devices: BeamstopCheckDevices):
    yield from bps.abs_set(
        devices.beamstop.selected_pos,
        BeamstopPositions.DATA_COLLECTION,
        group=_GROUP_POST_BEAMSTOP_OUT_CHECK,
    )

    LOGGER.info("Waiting for detector motion to complete...")
    yield from bps.wait(group=_GROUP_POST_BEAMSTOP_OUT_CHECK)


def _beamstop_out_check(
    devices: BeamstopCheckDevices,
    beamstop_threshold_uA: float,  # noqa: N803
    commissioning_mode_enabled: bool,
):
    ipin_beamstop_out_uA = yield from _check_ipin(devices)  # noqa: N806

    LOGGER.info(f"Beamstop out ipin = {ipin_beamstop_out_uA}uA")
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


def _beamstop_in_check(devices: BeamstopCheckDevices, beamstop_threshold_uA: float):  # noqa: N803
    ipin_in_beam_uA = yield from _check_ipin(devices)  # noqa: N806
    if ipin_in_beam_uA > beamstop_threshold_uA:
        raise BeamstopNotInPositionError(
            f"Ipin is too high at {ipin_in_beam_uA} - check that beamstop is "
            f"in the correct position."
        )


def _check_ipin(devices: BeamstopCheckDevices):
    yield from bps.abs_set(devices.sample_shutter, ZebraShutterState.OPEN, wait=True)
    yield from bps.sleep(1)  # wait for reading to settle

    ipin_current_uA = yield from bps.rd(devices.ipin.pin_readback)  # noqa: N806
    yield from bps.abs_set(devices.sample_shutter, ZebraShutterState.CLOSE, wait=True)
    return ipin_current_uA
