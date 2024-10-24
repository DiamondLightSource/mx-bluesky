"""
Extruder data collection
This version in python3 new Feb2021 by RLO
    - March 21 added logging and Eiger functionality
"""

import json
import logging
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from pprint import pformat
from time import sleep

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from blueapi.core import MsgGenerator
from dodal.beamlines import i24
from dodal.devices.hutch_shutter import HutchShutter, ShutterDemand
from dodal.devices.i24.aperture import Aperture
from dodal.devices.i24.beamstop import Beamstop
from dodal.devices.i24.dcm import DCM
from dodal.devices.i24.dual_backlight import DualBacklight
from dodal.devices.i24.i24_detector_motion import DetectorMotion
from dodal.devices.zebra import DISCONNECT, SOFT_IN3, Zebra

from mx_bluesky.beamlines.i24.serial import log
from mx_bluesky.beamlines.i24.serial.dcid import DCID
from mx_bluesky.beamlines.i24.serial.parameters import ExtruderParameters, SSXType
from mx_bluesky.beamlines.i24.serial.parameters.constants import (
    PARAM_FILE_NAME,
    PARAM_FILE_PATH,
)
from mx_bluesky.beamlines.i24.serial.setup_beamline import Pilatus, caget, caput, pv
from mx_bluesky.beamlines.i24.serial.setup_beamline import setup_beamline as sup
from mx_bluesky.beamlines.i24.serial.setup_beamline.setup_detector import (
    UnknownDetectorType,
    get_detector_type,
)
from mx_bluesky.beamlines.i24.serial.setup_beamline.setup_zebra_plans import (
    GATE_START,
    TTL_EIGER,
    TTL_PILATUS,
    arm_zebra,
    disarm_zebra,
    open_fast_shutter,
    reset_zebra_when_collection_done_plan,
    set_shutter_mode,
    setup_zebra_for_extruder_with_pump_probe_plan,
    setup_zebra_for_quickshot_plan,
)
from mx_bluesky.beamlines.i24.serial.write_nexus import call_nexgen

usage = "%(prog)s command [options]"
logger = logging.getLogger("I24ssx.extruder")

SAFE_DET_Z = 1480


def setup_logging():
    logfile = time.strftime("i24extruder_%d%B%y.log").lower()
    log.config(logfile)


def flush_print(text):
    sys.stdout.write(str(text))
    sys.stdout.flush()


@log.log_on_entry
def initialise_extruder(
    detector_stage: DetectorMotion = i24.detector_motion(wait_for_connection=False),
) -> MsgGenerator:
    setup_logging()
    logger.info("Initialise Parameters for extruder data collection on I24.")

    visit = caget(pv.ioc12_gp1)
    logger.info(f"Visit defined {visit}")

    # Define detector in use
    det_type = yield from get_detector_type(detector_stage)

    caput(pv.ioc12_gp2, "test")
    caput(pv.ioc12_gp3, "testrun")
    caput(pv.ioc12_gp4, "100")
    caput(pv.ioc12_gp5, "0.01")
    caput(pv.ioc12_gp6, 0)
    caput(pv.ioc12_gp8, 0)  # status PV do not reuse gp8 for something else
    caput(pv.ioc12_gp9, 0)
    caput(pv.ioc12_gp10, 0)
    caput(pv.ioc12_gp15, det_type.name)
    caput(pv.pilat_cbftemplate, 0)
    logger.info("Initialisation complete.")
    yield from bps.null()


@log.log_on_entry
def laser_check(
    mode: str,
    zebra: Zebra = i24.zebra(wait_for_connection=False),
    detector_stage: DetectorMotion = i24.detector_motion(wait_for_connection=False),
) -> MsgGenerator:
    """Plan to open the shutter and check the laser beam from the viewer by pressing \
        'Laser On' and 'Laser Off' buttons on the edm.

    The 'Laser on' button sets the correct OUT_TTL pv for the detector in use to \
    SOFT_IN1 and the shutter mode to auto.
    The 'Laser off' button disconnects the OUT_TTL pv set by the previous step and \
    resets the shutter mode to manual.

    WARNING. When using the laser with the extruder, some hardware changes need to be made.
    Because all four of the zebra ttl outputs are in use in this mode, when the \
    detector in use is the Eiger, the Pilatus cable is repurposed to trigger the light \
    source, and viceversa.
    """
    setup_logging()
    logger.debug(f"Laser check: {mode}")

    det_type = yield from get_detector_type(detector_stage)

    LASER_TTL = TTL_EIGER if isinstance(det_type, Pilatus) else TTL_PILATUS
    if mode == "laseron":
        yield from bps.abs_set(zebra.output.out_pvs[LASER_TTL], SOFT_IN3)
        yield from set_shutter_mode(zebra, "auto")

    if mode == "laseroff":
        yield from bps.abs_set(zebra.output.out_pvs[LASER_TTL], DISCONNECT)
        yield from set_shutter_mode(zebra, "manual")


@log.log_on_entry
def enter_hutch(
    detector_stage: DetectorMotion = i24.detector_motion(wait_for_connection=False),
) -> MsgGenerator:
    """Move the detector stage before entering hutch."""
    setup_logging()
    yield from bps.mv(detector_stage.z, SAFE_DET_Z)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    logger.debug("Detector moved.")


@log.log_on_entry
def write_parameter_file(detector_stage: DetectorMotion):
    """Writes a json parameter file that can later be parsed by the model."""
    param_file: Path = PARAM_FILE_PATH / PARAM_FILE_NAME
    logger.debug(f"Writing Parameter File to: {param_file}\n")

    det_type = yield from get_detector_type(detector_stage)
    logger.warning(f"DETECTOR TYPE: {det_type}")
    filename = caget(pv.ioc12_gp3)
    # If file name ends in a digit this causes processing/pilatus pain.
    # Append an underscore
    if det_type.name == "pilatus":
        m = re.search(r"\d+$", filename)
        if m is not None:
            # Note for future reference. Appending underscore causes more hassle and
            # high probability of users accidentally overwriting data. Use a dash
            filename = filename + "-"
            logger.info(
                f"Requested filename ends in a number. Appended dash: {filename}"
            )

    pump_status = bool(caget(pv.ioc12_gp6))
    pump_exp = float(caget(pv.ioc12_gp9)) if pump_status else None
    pump_delay = float(caget(pv.ioc12_gp10)) if pump_status else None

    params_dict = {
        "visit": log._read_visit_directory_from_file().as_posix(),  # noqa
        "directory": caget(pv.ioc12_gp2),
        "filename": filename,
        "exposure_time_s": float(caget(pv.ioc12_gp5)),
        "detector_distance_mm": float(caget(pv.ioc12_gp7)),
        "detector_name": str(det_type),
        "num_images": int(caget(pv.ioc12_gp4)),
        "pump_status": pump_status,
        "laser_dwell_s": pump_exp,
        "laser_delay_s": pump_delay,
    }
    with open(param_file, "w") as f:
        json.dump(params_dict, f, indent=4)

    logger.info("Parameters \n")
    logger.info(pformat(params_dict))
    yield from bps.null()


@log.log_on_entry
def main_extruder_plan(
    zebra: Zebra,
    aperture: Aperture,
    backlight: DualBacklight,
    beamstop: Beamstop,
    detector_stage: DetectorMotion,
    shutter: HutchShutter,
    dcm: DCM,
    parameters: ExtruderParameters,
    dcid: DCID,
    start_time: datetime,
) -> MsgGenerator:
    # Setting up the beamline
    logger.debug("Open hutch shutter")
    yield from bps.abs_set(shutter, ShutterDemand.OPEN, wait=True)

    yield from sup.setup_beamline_for_collection_plan(
        aperture, backlight, beamstop, wait=True
    )

    yield from sup.move_detector_stage_to_position_plan(
        detector_stage, parameters.detector_distance_mm
    )

    # For pixel detector
    filepath = parameters.collection_directory.as_posix()
    logger.debug(f"Filepath {filepath}")
    logger.debug(f"Filename {parameters.filename}")

    if parameters.detector_name == "pilatus":
        logger.info("Using pilatus mini cbf")
        caput(pv.pilat_cbftemplate, 0)
        logger.info(f"Pilatus quickshot setup: filepath {filepath}")
        logger.info(f"Pilatus quickshot setup: filepath {parameters.filename}")
        logger.info(
            f"Pilatus quickshot setup: number of images {parameters.num_images}"
        )
        logger.info(
            f"Pilatus quickshot setup: exposure time {parameters.exposure_time_s}"
        )

        if parameters.pump_status:
            logger.info("Pump probe extruder data collection")
            logger.info(f"Pump exposure time {parameters.laser_dwell_s}")
            logger.info(f"Pump delay time {parameters.laser_delay_s}")
            sup.pilatus(
                "fastchip",
                [
                    filepath,
                    parameters.filename,
                    parameters.num_images,
                    parameters.exposure_time_s,
                ],
            )
            yield from setup_zebra_for_extruder_with_pump_probe_plan(
                zebra,
                parameters.detector_name,
                parameters.exposure_time_s,
                parameters.num_images,
                parameters.laser_dwell_s,
                parameters.laser_delay_s,
                pulse1_delay=0.0,
                wait=True,
            )
        else:
            logger.info("Static experiment: no photoexcitation")
            sup.pilatus(
                "quickshot",
                [
                    filepath,
                    parameters.filename,
                    parameters.num_images,
                    parameters.exposure_time_s,
                ],
            )
            yield from setup_zebra_for_quickshot_plan(
                zebra, parameters.exposure_time_s, parameters.num_images, wait=True
            )

    elif parameters.detector_name == "eiger":
        logger.info("Using Eiger detector")

        logger.warning(
            """TEMPORARY HACK!
            Running a Single image pilatus data collection to create directory."""
        )  # See https://github.com/DiamondLightSource/mx_bluesky/issues/45
        num_shots = 1
        sup.pilatus(
            "quickshot-internaltrig",
            [filepath, parameters.filename, num_shots, parameters.exposure_time_s],
        )
        logger.debug("Sleep 2s waiting for pilatus to arm")
        sleep(2.5)
        caput(pv.pilat_acquire, "0")  # Disarm pilatus
        sleep(0.5)
        caput(pv.pilat_acquire, "1")  # Arm pilatus
        logger.debug("Pilatus data collection DONE")
        sup.pilatus("return to normal", None)
        logger.info("Pilatus back to normal. Single image pilatus data collection DONE")

        caput(pv.eiger_seqID, int(caget(pv.eiger_seqID)) + 1)
        logger.info(f"Eiger quickshot setup: filepath {filepath}")
        logger.info(f"Eiger quickshot setup: filepath {parameters.filename}")
        logger.info(f"Eiger quickshot setup: number of images {parameters.num_images}")
        logger.info(
            f"Eiger quickshot setup: exposure time {parameters.exposure_time_s}"
        )

        if parameters.pump_status:
            logger.info("Pump probe extruder data collection")
            logger.debug(f"Pump exposure time {parameters.laser_dwell_s}")
            logger.debug(f"Pump delay time {parameters.laser_delay_s}")
            sup.eiger(
                "triggered",
                [
                    filepath,
                    parameters.filename,
                    parameters.num_images,
                    parameters.exposure_time_s,
                ],
            )
            yield from setup_zebra_for_extruder_with_pump_probe_plan(
                zebra,
                parameters.detector_name,
                parameters.exposure_time_s,
                parameters.num_images,
                parameters.laser_dwell_s,
                parameters.laser_delay_s,
                pulse1_delay=0.0,
                wait=True,
            )
        else:
            logger.info("Static experiment: no photoexcitation")
            sup.eiger(
                "quickshot",
                [
                    filepath,
                    parameters.filename,
                    parameters.num_images,
                    parameters.exposure_time_s,
                ],
            )
            yield from setup_zebra_for_quickshot_plan(
                zebra, parameters.exposure_time_s, parameters.num_images, wait=True
            )
    else:
        err = f"Unknown Detector Type, det_type = {parameters.detector_name}"
        logger.error(err)
        raise UnknownDetectorType(err)

    # Do DCID creation BEFORE arming the detector
    dcid.generate_dcid(
        visit=parameters.visit.name,
        image_dir=parameters.collection_directory.as_posix(),
        start_time=start_time,
        num_images=parameters.num_images,
        exposure_time=parameters.exposure_time_s,
        pump_exposure_time=parameters.laser_dwell_s,
        pump_delay=parameters.laser_delay_s or 0,
        pump_status=int(parameters.pump_status),
    )

    # Collect
    logger.info("Fast shutter opening")
    yield from open_fast_shutter(zebra)
    if parameters.detector_name == "pilatus":
        logger.info("Pilatus acquire ON")
        caput(pv.pilat_acquire, 1)
    elif parameters.detector_name == "eiger":
        logger.info("Triggering Eiger NOW")
        caput(pv.eiger_trigger, 1)

    dcid.notify_start()

    if parameters.detector_name == "eiger":
        wavelength = yield from bps.rd(dcm.wavelength_in_a)
        logger.debug("Call nexgen server for nexus writing.")
        call_nexgen(None, start_time, parameters, wavelength, "extruder")

    timeout_time = time.time() + parameters.num_images * parameters.exposure_time_s + 10

    yield from arm_zebra(zebra)
    sleep(GATE_START)  # Sleep for the same length of gate_start, hard coded to 1
    i = 0
    text_list = ["|", "/", "-", "\\"]
    while True:
        line_of_text = "\r\t\t\t Waiting   " + 30 * (f"{text_list[i % 4]}")
        flush_print(line_of_text)
        sleep(0.5)
        i += 1
        zebra_arm_status = yield from bps.rd(zebra.pc.arm.armed)
        if zebra_arm_status == 0:  # not zebra.pc.is_armed():
            # As soon as zebra is disarmed, exit.
            # Epics updates this PV once the collection is done.
            logger.info("Zebra disarmed - Collection done.")
            break
        if time.time() >= timeout_time:
            logger.warning(
                """
                Something went wrong and data collection timed out. Aborting.
            """
            )
            raise TimeoutError("Data collection timed out.")

    logger.debug("Collection completed without errors.")


@log.log_on_entry
def collection_aborted_plan(
    zebra: Zebra, detector_name: str, dcid: DCID
) -> MsgGenerator:
    """A plan to run in case the collection is aborted before the end."""
    logger.warning("Data Collection Aborted")
    yield from disarm_zebra(zebra)  # If aborted/timed out zebra still armed
    if detector_name == "pilatus":
        caput(pv.pilat_acquire, 0)
    elif detector_name == "eiger":
        caput(pv.eiger_acquire, 0)
    sleep(0.5)
    end_time = datetime.now()
    dcid.collection_complete(end_time, aborted=True)


@log.log_on_entry
def tidy_up_at_collection_end_plan(
    zebra: Zebra,
    shutter: HutchShutter,
    parameters: ExtruderParameters,
    dcid: DCID,
) -> MsgGenerator:
    """A plan to tidy up at the end of a collection, successful or aborted.

    Args:
        zebra (Zebra): The Zebra device.
        shutter (HutchShutter): The HutchShutter device.
        parameters (ExtruderParameters): Collection parameters.
    """
    yield from reset_zebra_when_collection_done_plan(zebra)

    # Clean Up
    if parameters.detector_name == "pilatus":
        sup.pilatus("return-to-normal", None)
    elif parameters.detector_name == "eiger":
        sup.eiger("return-to-normal", None)
        logger.debug(f"{parameters.filename}_{caget(pv.eiger_seqID)}")
    logger.debug("End of Run")
    logger.debug("Close hutch shutter")
    yield from bps.abs_set(shutter, ShutterDemand.CLOSE, wait=True)

    dcid.notify_end()


@log.log_on_entry
def collection_complete_plan(
    collection_directory: Path, detector_name: str, dcid: DCID
) -> MsgGenerator:
    if detector_name == "pilatus":
        logger.info("Pilatus Acquire STOP")
        caput(pv.pilat_acquire, 0)
    elif detector_name == "eiger":
        logger.info("Eiger Acquire STOP")
        caput(pv.eiger_acquire, 0)
        caput(pv.eiger_ODcapture, "Done")

    sleep(0.5)

    end_time = datetime.now()
    dcid.collection_complete(end_time, aborted=False)
    logger.info(f"End Time = {end_time.ctime()}")

    # Copy parameter file
    shutil.copy2(
        PARAM_FILE_PATH / PARAM_FILE_NAME,
        collection_directory / PARAM_FILE_NAME,
    )
    yield from bps.null()


def run_extruder_plan(
    zebra: Zebra = i24.zebra(wait_for_connection=False),
    aperture: Aperture = i24.aperture(wait_for_connection=False),
    backlight: DualBacklight = i24.backlight(wait_for_connection=False),
    beamstop: Beamstop = i24.beamstop(wait_for_connection=False),
    detector_stage: DetectorMotion = i24.detector_motion(wait_for_connection=False),
    shutter: HutchShutter = i24.shutter(wait_for_connection=False),
    dcm: DCM = i24.dcm(wait_for_connection=False),
) -> MsgGenerator:
    setup_logging()
    start_time = datetime.now()
    logger.info(f"Collection start time: {start_time.ctime()}")

    yield from write_parameter_file(detector_stage)
    parameters = ExtruderParameters.from_file(PARAM_FILE_PATH / PARAM_FILE_NAME)

    # DCID - not generated yet
    dcid = DCID(
        emit_errors=False,
        ssx_type=SSXType.EXTRUDER,
        detector=parameters.detector_name,
    )

    yield from bpp.contingency_wrapper(
        main_extruder_plan(
            zebra=zebra,
            aperture=aperture,
            backlight=backlight,
            beamstop=beamstop,
            detector_stage=detector_stage,
            shutter=shutter,
            dcm=dcm,
            parameters=parameters,
            dcid=dcid,
            start_time=start_time,
        ),
        except_plan=lambda e: (
            yield from collection_aborted_plan(zebra, parameters.detector_name, dcid)
        ),
        else_plan=lambda: (
            yield from collection_complete_plan(
                parameters.collection_directory, parameters.detector_name, dcid
            )
        ),
        final_plan=lambda: (
            yield from tidy_up_at_collection_end_plan(zebra, shutter, parameters, dcid)
        ),
        auto_raise=False,
    )
