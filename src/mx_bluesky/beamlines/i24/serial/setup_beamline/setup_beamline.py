from pathlib import Path

import bluesky.plan_stubs as bps
from dodal.devices.detector.det_dim_constants import DetectorSizeConstants
from dodal.devices.i24.aperture import Aperture, AperturePositions
from dodal.devices.i24.beam_center import DetectorBeamCenter
from dodal.devices.i24.beamstop import Beamstop, BeamstopPositions
from dodal.devices.i24.dcm import DCM
from dodal.devices.i24.dual_backlight import BacklightPositions, DualBacklight
from dodal.devices.motors import YZStage
from dodal.devices.util.lookup_tables import (
    linear_interpolation_lut,
    parse_lookup_table,
)

from mx_bluesky.beamlines.i24.serial.log import SSX_LOGGER
from mx_bluesky.beamlines.i24.serial.setup_beamline import pv
from mx_bluesky.beamlines.i24.serial.setup_beamline.ca import caget, caput


def compute_beam_center_position_from_lut(
    lut_path: Path,
    detector_distance_mm: float,
    det_size_constants: DetectorSizeConstants,
) -> tuple[float, float]:
    """Calculate the beam center position for the detector distance \
    using the values in the lookup table for the conversion.
    """
    lut_values = parse_lookup_table(lut_path.as_posix())

    calc_x = linear_interpolation_lut(lut_values[0], lut_values[1])
    beam_x_mm = calc_x(detector_distance_mm)
    beam_x = (
        beam_x_mm
        * det_size_constants.det_size_pixels.width
        / det_size_constants.det_dimension.width
    )

    calc_y = linear_interpolation_lut(lut_values[0], lut_values[2])
    beam_y_mm = calc_y(detector_distance_mm)
    beam_y = (
        beam_y_mm
        * det_size_constants.det_size_pixels.height
        / det_size_constants.det_dimension.height
    )

    return beam_x, beam_y


def setup_beamline_for_collection_plan(
    aperture: Aperture,
    backlight: DualBacklight,
    beamstop: Beamstop,
    group: str = "setup_beamline_collect",
    wait: bool = True,
):
    SSX_LOGGER.debug("Setup beamline: collect.")
    yield from bps.abs_set(aperture.position, AperturePositions.IN, group=group)
    yield from bps.abs_set(backlight, BacklightPositions.OUT, group=group)
    yield from bps.sleep(3)  # Not sure needed - to test
    yield from bps.abs_set(
        beamstop.pos_select, BeamstopPositions.DATA_COLLECTION, group=group
    )
    yield from bps.abs_set(beamstop.y_rotation, 0, group=group)
    yield from bps.sleep(4)  # Not sure needed - to test

    if wait:
        yield from bps.wait(group=group)


def move_detector_stage_to_position_plan(
    detector_stage: YZStage,
    detector_distance: float,
):
    SSX_LOGGER.debug("Setup beamline: moving detector stage.")
    SSX_LOGGER.debug(
        f"Waiting for detector move. Detector distance: {detector_distance} mm."
    )
    yield from bps.mv(detector_stage.z, detector_distance)


def set_detector_beam_center_plan(
    beam_center_device: DetectorBeamCenter,
    beam_center_pixels: tuple[float, float],
    group: str = "set_beamcenter",
    wait: bool = True,
):
    """A small temporary plan to set up the beam center on the detector in use."""
    # NOTE This will be removed once the detectors are using ophyd_async devices
    # See https://github.com/DiamondLightSource/mx-bluesky/issues/62
    beam_position_x, beam_position_y = beam_center_pixels
    SSX_LOGGER.info(f"Setting beam center to: {beam_position_x}, {beam_position_y}")
    yield from bps.abs_set(beam_center_device.beam_x, beam_position_x, group=group)
    yield from bps.abs_set(beam_center_device.beam_y, beam_position_y, group=group)
    if wait:
        yield from bps.wait(group=group)


def eiger(
    action,
    args_list,
    dcm: DCM,
    detector_stage: YZStage,
):
    SSX_LOGGER.debug("***** Entering Eiger")
    SSX_LOGGER.info(f"Setup eiger - {action}")
    if args_list:
        for arg in args_list:
            SSX_LOGGER.debug(f"Argument: {arg}")
    det_z = yield from bps.rd(detector_stage.z.user_readback)
    caput(pv.eiger_detdist, str(det_z / 1000))
    dcm_wavelength_a = yield from bps.rd(dcm.wavelength_in_a.user_readback)
    caput(pv.eiger_wavelength, dcm_wavelength_a)
    caput(pv.eiger_omegaincr, 0.0)
    yield from bps.sleep(0.1)
    # Setup common to all collections ###
    caput(pv.eiger_filewriter, "No")
    caput(pv.eiger_stream, "Yes")
    caput(pv.eiger_monitor, "No")
    # caput(pv.eiger_datasource, 'None')
    caput(pv.eiger_statuspoll, "1 second")
    caput(pv.eiger_roi_mode, "Disabled")
    caput(pv.eiger_ff, "Enabled")
    caput(pv.eiger_compresstype, "bslz4")
    caput(pv.eiger_countmode, "Retrigger")
    caput(pv.eiger_autosum, "Enabled")
    caput(pv.eiger_hdrdetail, "All")

    # Quick set of images no coordinated motion
    if action == "quickshot":
        # Sends a single trigger to start data collection
        SSX_LOGGER.debug("Eiger quickshot")
        [filepath, filename, num_imgs, exptime] = args_list
        filename = filename + "_" + str(caget(pv.eiger_seq_id))
        caput(pv.eiger_od_filepath, filepath)
        yield from bps.sleep(0.1)
        caput(pv.eiger_od_filename, filename)
        yield from bps.sleep(0.1)
        acqtime = float(exptime) - 0.0000001
        caput(pv.eiger_acquiretime, str(acqtime))
        SSX_LOGGER.debug(f"Filepath was set as {filepath}")
        SSX_LOGGER.debug(f"Filename set as {filename}")
        SSX_LOGGER.debug(f"num_imgs {num_imgs}")
        SSX_LOGGER.debug(f"Exposure time set as {exptime} s")
        SSX_LOGGER.debug(f"Acquire time set as {acqtime} s")
        caput(pv.eiger_acquireperiod, str(exptime))
        caput(pv.eiger_numimages, str(num_imgs))
        caput(pv.eiger_imagemode, "Continuous")
        caput(pv.eiger_triggermode, "Internal Series")
        caput(pv.eiger_numtriggers, 1)
        caput(pv.eiger_manualtrigger, "Yes")
        yield from bps.sleep(1.0)
        # ODIN setup
        SSX_LOGGER.info("Setting up Odin")
        caput(pv.eiger_od_filename, filename)
        caput(pv.eiger_od_filepath, filepath)
        caput(pv.eiger_od_num_capture, str(num_imgs))
        caput(pv.eiger_od_filepath, filepath)
        eigerbdrbv = "UInt" + str(caget(pv.eiger_bitdepthrbv))
        caput(pv.eiger_od_datatype, eigerbdrbv)
        caput(pv.eiger_od_compress, "BSL24")
        yield from bps.sleep(1.0)
        # All done. Now get Odin to wait for data and start Eiger
        SSX_LOGGER.info("Done: Odin waiting for data")
        caput(pv.eiger_od_capture, "Capture")
        # If detector fails to arm first time can try twice with a sleep inbetween
        SSX_LOGGER.info("Arming Eiger")
        caput(pv.eiger_acquire, "1")
        # Will now wait for Manual trigger. Add the below line to your DAQ script ###
        # caput(pv.eiger_trigger, 1)

    if action == "triggered":
        # Send a trigger for every image. Records while TTL is high
        SSX_LOGGER.info("Eiger triggered")
        [filepath, filename, num_imgs, exptime] = args_list
        filename = filename + "_" + str(caget(pv.eiger_seq_id))
        caput(pv.eiger_od_filepath, filepath)
        yield from bps.sleep(0.1)
        caput(pv.eiger_od_filename, filename)
        yield from bps.sleep(0.1)
        acqtime = float(exptime) - 0.0000001
        caput(pv.eiger_acquiretime, str(acqtime))
        SSX_LOGGER.debug(f"Filepath was set as {filepath}")
        SSX_LOGGER.debug(f"Filename set as {filename}")
        SSX_LOGGER.debug(f"num_imgs {num_imgs}")
        SSX_LOGGER.debug(f"Exposure time set as {exptime} s")
        SSX_LOGGER.debug(f"Acquire time set as {acqtime} s")
        caput(pv.eiger_acquireperiod, str(exptime))
        caput(pv.eiger_numimages, 1)
        caput(pv.eiger_imagemode, "Continuous")
        caput(pv.eiger_triggermode, "External Enable")
        caput(pv.eiger_numtriggers, str(num_imgs))
        caput(pv.eiger_manualtrigger, "Yes")
        yield from bps.sleep(1.0)
        # ODIN setup #
        SSX_LOGGER.info("Setting up Odin")
        caput(pv.eiger_od_filename, filename)
        caput(pv.eiger_od_filepath, filepath)
        caput(pv.eiger_od_num_capture, str(num_imgs))
        caput(pv.eiger_od_filepath, filepath)
        eigerbdrbv = "UInt" + str(caget(pv.eiger_bitdepthrbv))
        caput(pv.eiger_od_datatype, eigerbdrbv)
        caput(pv.eiger_od_compress, "BSL24")
        yield from bps.sleep(1.0)
        # All done. Now get Odin to wait for data and start Eiger
        SSX_LOGGER.info("Done: Odin waiting for data")
        caput(pv.eiger_od_capture, "Capture")
        # If detector fails to arm first time can try twice with a sleep inbetween
        SSX_LOGGER.info("Arming Eiger")
        caput(pv.eiger_acquire, "1")
        # Will now wait for Manual trigger. Add the below line to your DAQ script
        # caput(pv.eiger_trigger, 1)

    # Put it all back to GDA acceptable defaults
    elif action == "return-to-normal":
        caput(pv.eiger_manualtrigger, "No")
        # caput(pv.eiger_seq_id, int(caget(pv.eiger_seq_id))+1)
    SSX_LOGGER.debug("***** leaving Eiger")
    yield from bps.sleep(0.1)
    return 0
