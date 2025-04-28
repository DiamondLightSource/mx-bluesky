from pathlib import Path

import bluesky.plan_stubs as bps
from dodal.beamlines import i24
from dodal.devices.detector.det_dim_constants import DetectorSizeConstants
from dodal.devices.i24.aperture import Aperture, AperturePositions
from dodal.devices.i24.beam_center import DetectorBeamCenter
from dodal.devices.i24.beamstop import Beamstop, BeamstopPositions
from dodal.devices.i24.dcm import DCM
from dodal.devices.i24.dual_backlight import BacklightPositions, DualBacklight
from dodal.devices.i24.i24_detector_motion import DetectorMotion
from dodal.devices.util.lookup_tables import (
    linear_interpolation_lut,
    parse_lookup_table,
)

from mx_bluesky.beamlines.i24.serial.log import SSX_LOGGER
from mx_bluesky.beamlines.i24.serial.setup_beamline import pv
from mx_bluesky.beamlines.i24.serial.setup_beamline.ca import caget, caput


def get_beam_center_device(detector_in_use: str) -> DetectorBeamCenter:
    if detector_in_use == "eiger":
        return i24.eiger_beam_center(connect_immediately=True)
    else:
        return i24.pilatus_beam_center(connect_immediately=True)


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
    detector_stage: DetectorMotion,
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


def modechange(action):
    """Mode Change"""
    # Pin Hand Mount
    if action == "Pin_hand_mount":
        caput(pv.bl_mp_select, "Out")
        caput(pv.aptr1_mp_select, "Manual Mounting")
        caput(pv.bs_mp_select, "Robot")
        caput(pv.vgon_omega, 0)
        caput(pv.vgon_kappa, 0)
        caput(pv.vgon_phi, 0)
        caput(pv.vgon_pinxs, 0)
        caput(pv.vgon_pinzs, 0)
        caput(pv.fluo_trans, "OUT")
        caput(pv.cstrm_p1701, 0)
        caput(pv.cstrm_mp_select, "Out")
        SSX_LOGGER.debug("Pin Hand Mount Done")

    # Pin Room Tempreature Hand Mount
    elif action == "Pin_rt_hand_mount":
        caput(pv.cstrm_p1701, 0)
        caput(pv.cstrm_mp_select, "Away")
        caput(pv.bl_mp_select, "Out")
        caput(pv.aptr1_mp_select, "Manual Mounting")
        caput(pv.bs_mp_select, "Robot")
        caput(pv.vgon_omega, 0)
        caput(pv.vgon_kappa, 0)
        caput(pv.vgon_phi, 0)
        caput(pv.vgon_pinxs, 0)
        caput(pv.vgon_pinzs, 0)
        caput(pv.fluo_trans, "OUT")
        SSX_LOGGER.debug("RT Pin Hand Mount Done")

    # Pin Data Collection
    elif action == "Pin_data_collection":
        caput(pv.cstrm_p1701, 0)
        caput(pv.cstrm_mp_select, "In")
        caput(pv.aptr1_mp_select, "In")
        caput(pv.vgon_omega, 0)
        caput(pv.vgon_kappa, 0)
        caput(pv.vgon_phi, 0)
        caput(pv.vgon_pinxs, 0)
        # caput(pv.vgon_pinyh, 0)
        caput(pv.vgon_pinzs, 0)
        caput(pv.fluo_trans, "OUT")
        caput(pv.bs_roty, 0)
        yield from bps.sleep(0.5)
        caput(pv.bs_mp_select, "Data Collection")
        yield from bps.sleep(2.3)
        caput(pv.bl_mp_select, "In")
        SSX_LOGGER.debug("Pin Data Collection Done")

    # Pin Room Tempreature Data Collection
    elif action == "Pin_rt_data_collection":
        SSX_LOGGER.debug("RT Mode")
        caput(pv.cstrm_p1701, 0)
        caput(pv.cstrm_mp_select, "Away")
        caput(pv.aptr1_mp_select, "In")
        caput(pv.vgon_omega, 0)
        caput(pv.vgon_kappa, 0)
        caput(pv.vgon_phi, 0)
        caput(pv.vgon_pinxs, 0)
        caput(pv.vgon_pinyh, 0)
        caput(pv.vgon_pinzs, 0)
        caput(pv.fluo_trans, "OUT")
        yield from bps.sleep(0.1)
        caput(pv.bs_roty, 0)
        yield from bps.sleep(2.6)
        caput(pv.bl_mp_select, "In")
        caput(pv.bs_mp_select, "Data Collection")
        SSX_LOGGER.debug("RT Data Collection Done")

    # Tray Hand Mount
    elif action == "Tray_hand_mount":
        caput(pv.ttab_x, 2.0)
        caput(pv.hgon_trayys, 0.0)
        caput(pv.hgon_omega, 0.0)
        caput(pv.fluo_trans, "OUT")
        caput(pv.bl_mp_select, "Out")
        yield from bps.sleep(1)
        caput(pv.aptr1_mp_select, "Manual Mounting")
        caput(pv.bs_mp_select, "Tray Mount")
        while float(caget(pv.ttab_x + ".RBV")) > 3:
            yield from bps.sleep(1)
        SSX_LOGGER.debug("Tray Hand Mount Done")

    # Tray Robot Load. This action needs to be reviewed and revised
    elif action == "Tray_robot_load":
        # Middle of black circle
        caput(pv.ttab_x, 79.2)
        caput(pv.hgon_trayys, -7.00)
        caput(pv.hgon_trayzs, -1.10)
        caput(pv.hgon_omega, 0.0)
        caput(pv.fluo_trans, "OUT")
        caput(pv.aptr1_mp_select, "In")
        caput(pv.bl_mp_select, "Out")
        yield from bps.sleep(1)
        caput(pv.bs_roty, 0)
        yield from bps.sleep(1)
        caput(pv.bs_mp_select, "Robot")
        yield from bps.sleep(1)
        caput(pv.bs_mp_select, "Data Collection Far")
        yield from bps.sleep(1)
        caput(pv.bs_roty, 0)
        yield from bps.sleep(4)
        caput(pv.bl_mp_select, "In")
        SSX_LOGGER.debug("Tray Robot Mount Done")

    # Tray Data Collection
    elif action == "Tray_data_collection":
        SSX_LOGGER.debug("This should be E11 on the test tray (CrystalQuickX)")
        caput(pv.ttab_x, 37.4)
        caput(pv.hgon_trayys, -8.0)
        caput(pv.hgon_trayzs, -2.1)
        caput(pv.aptr1_mp_select, "In")
        caput(pv.fluo_trans, "OUT")
        caput(pv.bl_mp_select, "Out")
        yield from bps.sleep(1)
        caput(pv.bs_roty, 0)
        yield from bps.sleep(1)
        caput(pv.bs_mp_select, "Robot")
        yield from bps.sleep(1)
        caput(pv.bs_mp_select, "Data Collection")
        yield from bps.sleep(1)
        caput(pv.bs_roty, 0)
        yield from bps.sleep(4)
        caput(pv.bl_mp_select, "In")
        SSX_LOGGER.debug("Tray Data Collection Done")

    # Pin Switch to Tray
    elif action == "Pin_switch2tray":
        caput(pv.cstrm_p1701, 0)
        caput(pv.cstrm_mp_select, "Away")
        caput(pv.aptr1_mp_select, "Manual Mounting")
        caput(pv.bl_mp_select, "Out")
        caput(pv.hgon_omega, 0.0)
        caput(pv.ttab_x, 0)
        caput(pv.hgon_trayys, 0.0)
        caput(pv.hgon_trayzs, 0.0)
        caput(pv.ptab_y, -90)
        caput(pv.fluo_trans, "OUT")
        caput(pv.vgon_omega, 0)
        caput(pv.vgon_kappa, 0)
        caput(pv.vgon_phi, 0)
        caput(pv.vgon_pinxs, 0)
        caput(pv.vgon_pinyh, 0)
        caput(pv.vgon_pinzs, 0)
        while float(caget(pv.ttab_x + ".RBV")) > 1:
            SSX_LOGGER.debug(f"moving ttab_x {caget(pv.ttab_x)}")
            yield from bps.sleep(0.1)
        while caget(pv.fluo_out_limit) == "OFF":
            SSX_LOGGER.debug("waiting on fluorescence detector")
            yield from bps.sleep(0.1)
        while caget(pv.bl_mp_select) != "Out":
            SSX_LOGGER.debug("waiting on back light to move to out")
            yield from bps.sleep(0.1)
        caput(pv.bs_mp_select, "Robot")
        caput(pv.bs_roty, 0)
        while float(caget(pv.ptab_y + ".RBV")) > -89.0:
            yield from bps.sleep(1)
        SSX_LOGGER.debug("Switch To Tray Done")

    # Tray Switch to Pin
    elif action == "Tray_switch2pin":
        caput(pv.ttab_x, 0.0)
        # Supposed to absorb pin laser
        caput(pv.hgon_trayys, 0.0)
        caput(pv.hgon_trayzs, 0.0)
        while float(caget(pv.ttab_x + ".RBV")) > 1.0:
            yield from bps.sleep(1)
        caput(pv.ptab_y, 0)
        while float(caget(pv.ptab_y + ".RBV")) < -1.0:
            yield from bps.sleep(1)
        yield from modechange("Pin_data_collection")
        SSX_LOGGER.debug("Switch To Pin Done")
    else:
        SSX_LOGGER.debug(f"Unknown action: {action}")
    return 1


def pilatus(action, args_list):
    SSX_LOGGER.debug("***** Entering Pilatus")
    SSX_LOGGER.info(f"Setup pilatus - {action}")
    if args_list:
        for arg in args_list:
            SSX_LOGGER.debug(f"Argument: {arg}")

    caput(pv.pilat_detdist, caget(pv.det_z))
    caput(pv.pilat_filtertrasm, caget(pv.attn_match))

    # Fixed Target stage (very fast start and stop w/ triggering from GeoBrick
    if action == "fastchip":
        [filepath, filename, total_numb_imgs, exptime] = args_list
        rampath = filepath.replace("dls/i24/data", "ramdisk")
        acqtime = float(exptime) - 0.001
        SSX_LOGGER.debug(f"Filepath was set as {filepath}")
        SSX_LOGGER.debug(f"Rampath set as {rampath}")
        SSX_LOGGER.debug(f"Filename set as {filename}")
        SSX_LOGGER.debug(f"total_numb_imgs {total_numb_imgs}")
        SSX_LOGGER.debug(f"Exposure time set as {exptime} s")
        SSX_LOGGER.debug(f"Acquire time set as {acqtime} s")
        caput(pv.pilat_startangle, 0.0)
        caput(pv.pilat_angleincr, 0.0)
        caput(pv.pilat_omegaincr, 0.0)
        caput(pv.pilat_filepath, rampath + "/")
        caput(pv.pilat_filename, filename)
        caput(pv.pilat_numimages, str(total_numb_imgs))
        caput(pv.pilat_acquiretime, str(acqtime))
        caput(pv.pilat_acquireperiod, str(exptime))
        caput(pv.pilat_imagemode, "Single")
        caput(pv.pilat_triggermode, "Mult. Trigger")
        caput(pv.pilat_delaytime, 0)

    # Quick set of images no coordinated motion
    elif action == "quickshot":
        SSX_LOGGER.debug("quickshot")
        [filepath, filename, num_imgs, exptime] = args_list
        rampath = filepath.replace("dls/i24/data", "ramdisk")
        caput(pv.pilat_filepath, rampath)
        yield from bps.sleep(0.1)
        caput(pv.pilat_filename, filename)
        yield from bps.sleep(0.1)
        acqtime = float(exptime) - 0.001
        caput(pv.pilat_acquiretime, str(acqtime))
        caput(pv.pilat_acquireperiod, str(exptime))
        SSX_LOGGER.debug(f"Filepath was set as {filepath}")
        SSX_LOGGER.debug(f"Rampath set as {rampath}")
        SSX_LOGGER.debug(f"Filename set as {filename}")
        SSX_LOGGER.debug(f"num_imgs {num_imgs}")
        SSX_LOGGER.debug(f"Exposure time set as {exptime} s")
        SSX_LOGGER.debug(f"Acquire time set as {acqtime} s")
        SSX_LOGGER.debug("Pilatus takes time apprx 2sec")
        yield from bps.sleep(2)
        caput(pv.pilat_delaytime, 0.00)
        caput(pv.pilat_numimages, str(num_imgs))
        caput(pv.pilat_imagemode, "Continuous")
        caput(pv.pilat_triggermode, "Ext. Trigger")
        yield from bps.sleep(0.2)

    elif action == "quickshot-internaltrig":
        SSX_LOGGER.debug("quickshot-internaltrig")
        [filepath, filename, num_imgs, exptime] = args_list
        rampath = filepath.replace("dls/i24/data", "ramdisk")
        caput(pv.pilat_filepath, rampath)
        yield from bps.sleep(0.1)
        caput(pv.pilat_filename, filename)
        yield from bps.sleep(0.1)
        acqtime = float(exptime) - 0.001
        caput(pv.pilat_acquiretime, str(acqtime))
        caput(pv.pilat_acquireperiod, str(exptime))
        SSX_LOGGER.debug(f"Filepath was set as {filepath}")
        SSX_LOGGER.debug(f"Rampath set as {rampath}")
        SSX_LOGGER.debug(f"Filename set as {filename}")
        SSX_LOGGER.debug(f"num_imgs {num_imgs}")
        SSX_LOGGER.debug(f"Exposure time set as {exptime} s")
        SSX_LOGGER.debug(f"Acquire time set as {acqtime} s")
        SSX_LOGGER.debug("Pilatus takes time apprx 2sec")
        yield from bps.sleep(2)
        caput(pv.pilat_delaytime, 0.00)
        caput(pv.pilat_numimages, str(num_imgs))
        caput(pv.pilat_imagemode, "Continuous")
        caput(pv.pilat_triggermode, "Internal")
        yield from bps.sleep(0.2)

    # Put it all back to GDA acceptable defaults
    elif action == "return to normal":
        caput(pv.pilat_imagemode, "Continuous")
        caput(pv.pilat_triggermode, "Ext. Trigger")
        caput(pv.pilat_numexpimage, 1)
    SSX_LOGGER.debug("***** leaving pilatus")
    yield from bps.sleep(0.1)
    return 0


def eiger(action, args_list, dcm: DCM):
    SSX_LOGGER.debug("***** Entering Eiger")
    SSX_LOGGER.info(f"Setup eiger - {action}")
    if args_list:
        for arg in args_list:
            SSX_LOGGER.debug(f"Argument: {arg}")
    caput(pv.eiger_detdist, str(float(caget(pv.det_z)) / 1000))
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
    caput(pv.eiger_ROImode, "Disabled")
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
        filename = filename + "_" + str(caget(pv.eiger_seqID))
        caput(pv.eiger_ODfilepath, filepath)
        yield from bps.sleep(0.1)
        caput(pv.eiger_ODfilename, filename)
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
        caput(pv.eiger_ODfilename, filename)
        caput(pv.eiger_ODfilepath, filepath)
        caput(pv.eiger_ODnumcapture, str(num_imgs))
        caput(pv.eiger_ODfilepath, filepath)
        eigerbdrbv = "UInt" + str(caget(pv.eiger_bitdepthrbv))
        caput(pv.eiger_ODdatatype, eigerbdrbv)
        caput(pv.eiger_ODcompress, "BSL24")
        yield from bps.sleep(1.0)
        # All done. Now get Odin to wait for data and start Eiger
        SSX_LOGGER.info("Done: Odin waiting for data")
        caput(pv.eiger_ODcapture, "Capture")
        # If detector fails to arm first time can try twice with a sleep inbetween
        SSX_LOGGER.info("Arming Eiger")
        caput(pv.eiger_acquire, "1")
        # Will now wait for Manual trigger. Add the below line to your DAQ script ###
        # caput(pv.eiger_trigger, 1)

    if action == "triggered":
        # Send a trigger for every image. Records while TTL is high
        SSX_LOGGER.info("Eiger triggered")
        [filepath, filename, num_imgs, exptime] = args_list
        filename = filename + "_" + str(caget(pv.eiger_seqID))
        caput(pv.eiger_ODfilepath, filepath)
        yield from bps.sleep(0.1)
        caput(pv.eiger_ODfilename, filename)
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
        caput(pv.eiger_ODfilename, filename)
        caput(pv.eiger_ODfilepath, filepath)
        caput(pv.eiger_ODnumcapture, str(num_imgs))
        caput(pv.eiger_ODfilepath, filepath)
        eigerbdrbv = "UInt" + str(caget(pv.eiger_bitdepthrbv))
        caput(pv.eiger_ODdatatype, eigerbdrbv)
        caput(pv.eiger_ODcompress, "BSL24")
        yield from bps.sleep(1.0)
        # All done. Now get Odin to wait for data and start Eiger
        SSX_LOGGER.info("Done: Odin waiting for data")
        caput(pv.eiger_ODcapture, "Capture")
        # If detector fails to arm first time can try twice with a sleep inbetween
        SSX_LOGGER.info("Arming Eiger")
        caput(pv.eiger_acquire, "1")
        # Will now wait for Manual trigger. Add the below line to your DAQ script
        # caput(pv.eiger_trigger, 1)

    # Put it all back to GDA acceptable defaults
    elif action == "return-to-normal":
        caput(pv.eiger_manualtrigger, "No")
        # caput(pv.eiger_seqID, int(caget(pv.eiger_seqID))+1)
    SSX_LOGGER.debug("***** leaving Eiger")
    yield from bps.sleep(0.1)
    return 0


def xspress3(action, args_list):
    SSX_LOGGER.debug("***** Entering xspress3")
    SSX_LOGGER.info(f"xspress3 - {action}")
    if args_list:
        for arg in args_list:
            SSX_LOGGER.debug(f"Argument: {arg}")

    if action == "stop-and-start":
        [exp_time, lo, hi] = args_list
        caput(pv.xsp3_triggermode, "Internal")
        caput(pv.xsp3_numimages, 1)
        caput(pv.xsp3_acquiretime, exp_time)
        caput(pv.xsp3_c1_mca_roi1_llm, lo)
        caput(pv.xsp3_c1_mca_roi1_hlm, hi)
        yield from bps.sleep(0.2)
        caput(pv.xsp3_c1_mca_roi1_llm, lo)
        caput(pv.xsp3_c1_mca_roi1_hlm, hi)
        yield from bps.sleep(0.2)
        caput(pv.xsp3_erase, 0)

    elif action == "on-the-fly":
        [num_frms, lo, hi] = args_list
        caput(pv.xsp3_triggermode, "TTL Veto Only")
        caput(pv.xsp3_numimages, num_frms)
        caput(pv.xsp3_c1_mca_roi1_llm, lo)
        caput(pv.xsp3_c1_mca_roi1_hlm, hi)
        yield from bps.sleep(0.2)
        caput(pv.xsp3_c1_mca_roi1_llm, lo)
        caput(pv.xsp3_c1_mca_roi1_hlm, hi)
        yield from bps.sleep(0.2)
        caput(pv.xsp3_erase, 0)

    elif action == "return-to-normal":
        caput(pv.xsp3_triggermode, "TTL Veto Only")
        caput(pv.xsp3_numimages, 1)
        caput(pv.xsp3_acquiretime, 1)
        caput(pv.xsp3_c1_mca_roi1_llm, 0)
        caput(pv.xsp3_c1_mca_roi1_hlm, 0)
        caput(pv.xsp3_erase, 0)

    else:
        SSX_LOGGER.error("Unknown action for xspress3 method:", action)

    yield from bps.sleep(0.1)
    SSX_LOGGER.debug("***** leaving xspress3")
    return 1
