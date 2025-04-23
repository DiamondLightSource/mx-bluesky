"""
Extruder data collection
This version in python3 new Feb2021 by RLO
    - March 21 added logging and Eiger functionality
"""

import re
import sys
import time
from datetime import datetime
from pathlib import Path
from pprint import pformat

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.attenuator.attenuator import ReadOnlyAttenuator
from dodal.devices.hutch_shutter import HutchShutter, ShutterDemand
from dodal.devices.i24.aperture import Aperture
from dodal.devices.i24.beam_center import DetectorBeamCenter
from dodal.devices.i24.beamstop import Beamstop
from dodal.devices.i24.dcm import DCM
from dodal.devices.i24.dual_backlight import DualBacklight
from dodal.devices.i24.focus_mirrors import FocusMirrorsMode
from dodal.devices.i24.i24_detector_motion import DetectorMotion
from dodal.devices.zebra.zebra import Zebra

from mx_bluesky.beamlines.i24.serial.dcid import (
    DCID,
    get_pilatus_filename_template_from_device,
    read_beam_info_from_hardware,
)
from mx_bluesky.beamlines.i24.serial.log import (
    SSX_LOGGER,
    _read_visit_directory_from_file,
    log_on_entry,
)
from mx_bluesky.beamlines.i24.serial.parameters import ExtruderParameters
from mx_bluesky.beamlines.i24.serial.parameters.constants import BEAM_CENTER_LUT_FILES
from mx_bluesky.beamlines.i24.serial.setup_beamline import Pilatus, caget, caput, pv
from mx_bluesky.beamlines.i24.serial.setup_beamline import setup_beamline as sup
from mx_bluesky.beamlines.i24.serial.setup_beamline.setup_detector import (
    UnknownDetectorType,
    get_detector_type,
)
from mx_bluesky.beamlines.i24.serial.setup_beamline.setup_zebra_plans import (
    GATE_START,
    arm_zebra,
    disarm_zebra,
    open_fast_shutter,
    reset_zebra_when_collection_done_plan,
    set_shutter_mode,
    setup_zebra_for_extruder_with_pump_probe_plan,
    setup_zebra_for_quickshot_plan,
)
from mx_bluesky.beamlines.i24.serial.write_nexus import call_nexgen

SAFE_DET_Z = 1480


def flush_print(text):
    sys.stdout.write(str(text))
    sys.stdout.flush()


@log_on_entry
def initialise_extruder(
    detector_stage: DetectorMotion = inject("detector_motion"),
) -> MsgGenerator:
    SSX_LOGGER.info("Initialise Parameters for extruder data collection on I24.")

    visit = caget(pv.ioc13_gp1)
    SSX_LOGGER.info(f"Visit defined {visit}")

    # Define detector in use
    det_type = yield from get_detector_type(detector_stage)

    caput(pv.ioc13_gp2, "test")
    caput(pv.ioc13_gp3, "testrun")
    caput(pv.ioc13_gp4, "100")
    caput(pv.ioc13_gp5, "0.01")
    caput(pv.ioc13_gp6, 0)
    caput(pv.ioc13_gp8, 0)  # status PV do not reuse gp8 for something else
    caput(pv.ioc13_gp9, 0)
    caput(pv.ioc13_gp10, 0)
    caput(pv.ioc13_gp15, det_type.name)
    caput(pv.pilat_cbftemplate, 0)
    SSX_LOGGER.info("Initialisation complete.")
    yield from bps.null()


@log_on_entry
def laser_check(
    mode: str,
    zebra: Zebra = inject("zebra"),
    detector_stage: DetectorMotion = inject("detector_motion"),
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
    SSX_LOGGER.debug(f"Laser check: {mode}")

    det_type = yield from get_detector_type(detector_stage)

    LASER_TTL = (
        zebra.mapping.outputs.TTL_EIGER
        if isinstance(det_type, Pilatus)
        else zebra.mapping.outputs.TTL_PILATUS
    )

    if mode == "laseron":
        yield from bps.abs_set(
            zebra.output.out_pvs[LASER_TTL], zebra.mapping.sources.SOFT_IN3
        )
        yield from set_shutter_mode(zebra, "auto")

    if mode == "laseroff":
        yield from bps.abs_set(
            zebra.output.out_pvs[LASER_TTL], zebra.mapping.sources.DISCONNECT
        )
        yield from set_shutter_mode(zebra, "manual")


@log_on_entry
def enter_hutch(
    detector_stage: DetectorMotion = inject("detector_motion"),
) -> MsgGenerator:
    """Move the detector stage before entering hutch."""
    yield from bps.mv(detector_stage.z, SAFE_DET_Z)
    SSX_LOGGER.debug("Detector moved.")


@log_on_entry
def read_parameters(detector_stage: DetectorMotion, attenuator: ReadOnlyAttenuator):
    """ Read the parameters from user input and create the parameter model for an \
        extruder collection.

    Args:
        detector_stage (DetectorMotion): The detector stage device.
        attenuator (ReadOnlyAttenuator): A read-only attenuator device to get the \
            transmission value.

    Returns:
        ExtruderParameters: Parameter model for extruder collections

    """
    SSX_LOGGER.info("Creating parameter model from input.")

    det_type = yield from get_detector_type(detector_stage)
    SSX_LOGGER.warning(f"DETECTOR TYPE: {det_type}")
    filename = caget(pv.ioc13_gp3)
    # If file name ends in a digit this causes processing/pilatus pain.
    # Append an underscore
    if det_type.name == "pilatus":
        m = re.search(r"\d+$", filename)
        if m is not None:
            # Note for future reference. Appending underscore causes more hassle and
            # high probability of users accidentally overwriting data. Use a dash
            filename = filename + "-"
            SSX_LOGGER.info(
                f"Requested filename ends in a number. Appended dash: {filename}"
            )

    transmission = yield from bps.rd(attenuator.actual_transmission)

    pump_status = bool(int(caget(pv.ioc13_gp6)))
    pump_exp = float(caget(pv.ioc13_gp9)) if pump_status else 0.0
    pump_delay = float(caget(pv.ioc13_gp10)) if pump_status else 0.0

    params_dict = {
        "visit": _read_visit_directory_from_file().as_posix(),  # noqa
        "directory": caget(pv.ioc13_gp2),
        "filename": filename,
        "exposure_time_s": float(caget(pv.ioc13_gp5)),
        "detector_distance_mm": float(caget(pv.ioc13_gp7)),
        "detector_name": str(det_type),
        "transmission": transmission,
        "num_images": int(caget(pv.ioc13_gp4)),
        "pump_status": pump_status,
        "laser_dwell_s": pump_exp,
        "laser_delay_s": pump_delay,
    }

    SSX_LOGGER.info("Parameters \n")
    SSX_LOGGER.info(pformat(params_dict))
    yield from bps.null()
    return ExtruderParameters(**params_dict)


@log_on_entry
def main_extruder_plan(
    zebra: Zebra,
    aperture: Aperture,
    backlight: DualBacklight,
    beamstop: Beamstop,
    detector_stage: DetectorMotion,
    shutter: HutchShutter,
    dcm: DCM,
    mirrors: FocusMirrorsMode,
    beam_center_device: DetectorBeamCenter,
    parameters: ExtruderParameters,
    dcid: DCID,
    start_time: datetime,
) -> MsgGenerator:
    beam_center_pixels = sup.compute_beam_center_position_from_lut(
        BEAM_CENTER_LUT_FILES[parameters.detector_name],
        parameters.detector_distance_mm,
        parameters.detector_size_constants,
    )
    yield from sup.set_detector_beam_center_plan(
        beam_center_device,
        beam_center_pixels,
    )

    # Setting up the beamline
    SSX_LOGGER.info("Open hutch shutter")
    yield from bps.abs_set(shutter, ShutterDemand.OPEN, wait=True)

    yield from sup.setup_beamline_for_collection_plan(
        aperture, backlight, beamstop, wait=True
    )

    yield from sup.move_detector_stage_to_position_plan(
        detector_stage, parameters.detector_distance_mm
    )

    # For pixel detector
    filepath = parameters.collection_directory.as_posix()
    SSX_LOGGER.debug(f"Filepath {filepath}")
    SSX_LOGGER.debug(f"Filename {parameters.filename}")

    if parameters.detector_name == "pilatus":
        SSX_LOGGER.info("Using pilatus mini cbf")
        caput(pv.pilat_cbftemplate, 0)
        SSX_LOGGER.info(f"Pilatus quickshot setup: filepath {filepath}")
        SSX_LOGGER.info(f"Pilatus quickshot setup: filepath {parameters.filename}")
        SSX_LOGGER.info(
            f"Pilatus quickshot setup: number of images {parameters.num_images}"
        )
        SSX_LOGGER.info(
            f"Pilatus quickshot setup: exposure time {parameters.exposure_time_s}"
        )

        if parameters.pump_status:
            SSX_LOGGER.info("Pump probe extruder data collection")
            SSX_LOGGER.info(f"Pump exposure time {parameters.laser_dwell_s}")
            SSX_LOGGER.info(f"Pump delay time {parameters.laser_delay_s}")
            yield from sup.pilatus(
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
            SSX_LOGGER.info("Static experiment: no photoexcitation")
            yield from sup.pilatus(
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
        SSX_LOGGER.info("Using Eiger detector")

        SSX_LOGGER.debug(f"Creating the directory for the collection in {filepath}.")

        caput(pv.eiger_seqID, int(caget(pv.eiger_seqID)) + 1)
        SSX_LOGGER.info(f"Eiger quickshot setup: filepath {filepath}")
        SSX_LOGGER.info(f"Eiger quickshot setup: filepath {parameters.filename}")
        SSX_LOGGER.info(
            f"Eiger quickshot setup: number of images {parameters.num_images}"
        )
        SSX_LOGGER.info(
            f"Eiger quickshot setup: exposure time {parameters.exposure_time_s}"
        )

        if parameters.pump_status:
            SSX_LOGGER.info("Pump probe extruder data collection")
            SSX_LOGGER.debug(f"Pump exposure time {parameters.laser_dwell_s}")
            SSX_LOGGER.debug(f"Pump delay time {parameters.laser_delay_s}")
            yield from sup.eiger(
                "triggered",
                [
                    filepath,
                    parameters.filename,
                    parameters.num_images,
                    parameters.exposure_time_s,
                ],
                dcm,
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
            SSX_LOGGER.info("Static experiment: no photoexcitation")
            yield from sup.eiger(
                "quickshot",
                [
                    filepath,
                    parameters.filename,
                    parameters.num_images,
                    parameters.exposure_time_s,
                ],
                dcm,
            )
            yield from setup_zebra_for_quickshot_plan(
                zebra, parameters.exposure_time_s, parameters.num_images, wait=True
            )
    else:
        err = f"Unknown Detector Type, det_type = {parameters.detector_name}"
        SSX_LOGGER.error(err)
        raise UnknownDetectorType(err)

    beam_settings = yield from read_beam_info_from_hardware(
        dcm, mirrors, beam_center_device, parameters.detector_name
    )

    # Do DCID creation BEFORE arming the detector
    if parameters.detector_name == "eiger":
        filetemplate = f"{parameters.filename}.nxs"
    else:
        filetemplate = yield from get_pilatus_filename_template_from_device()
    dcid.generate_dcid(
        beam_settings=beam_settings,
        image_dir=parameters.collection_directory.as_posix(),
        file_template=filetemplate,
        num_images=parameters.num_images,
        start_time=start_time,
        pump_probe=parameters.pump_status,
    )

    # Collect
    SSX_LOGGER.info("Fast shutter opening")
    yield from open_fast_shutter(zebra)
    if parameters.detector_name == "pilatus":
        SSX_LOGGER.info("Pilatus acquire ON")
        caput(pv.pilat_acquire, 1)
    elif parameters.detector_name == "eiger":
        SSX_LOGGER.info("Triggering Eiger NOW")
        caput(pv.eiger_trigger, 1)

    dcid.notify_start()

    if parameters.detector_name == "eiger":
        SSX_LOGGER.debug("Call nexgen server for nexus writing.")
        beam_x = yield from bps.rd(beam_center_device.beam_x)
        beam_y = yield from bps.rd(beam_center_device.beam_y)
        call_nexgen(
            None,
            parameters,
            beam_settings.wavelength_in_a,
            (beam_x, beam_y),
            start_time,
        )

    timeout_time = time.time() + parameters.num_images * parameters.exposure_time_s + 10

    yield from arm_zebra(zebra)
    yield from bps.sleep(
        GATE_START
    )  # bps.sleep for the same length of gate_start, hard coded to 1
    i = 0
    text_list = ["|", "/", "-", "\\"]
    while True:
        line_of_text = "\r\t\t\t Waiting   " + 30 * (f"{text_list[i % 4]}")
        flush_print(line_of_text)
        yield from bps.sleep(0.5)
        i += 1
        zebra_arm_status = yield from bps.rd(zebra.pc.arm.armed)
        if zebra_arm_status == 0:  # not zebra.pc.is_armed():
            # As soon as zebra is disarmed, exit.
            # Epics updates this PV once the collection is done.
            SSX_LOGGER.info("Zebra disarmed - Collection done.")
            break
        if time.time() >= timeout_time:
            SSX_LOGGER.warning(
                """
                Something went wrong and data collection timed out. Aborting.
            """
            )
            raise TimeoutError("Data collection timed out.")

    SSX_LOGGER.info("Collection completed without errors.")


@log_on_entry
def collection_aborted_plan(
    zebra: Zebra, detector_name: str, dcid: DCID
) -> MsgGenerator:
    """A plan to run in case the collection is aborted before the end."""
    SSX_LOGGER.warning("Data Collection Aborted")
    yield from disarm_zebra(zebra)  # If aborted/timed out zebra still armed
    if detector_name == "pilatus":
        caput(pv.pilat_acquire, 0)
    elif detector_name == "eiger":
        caput(pv.eiger_acquire, 0)
    yield from bps.sleep(0.5)
    end_time = datetime.now()
    dcid.collection_complete(end_time, aborted=True)


@log_on_entry
def tidy_up_at_collection_end_plan(
    zebra: Zebra,
    shutter: HutchShutter,
    parameters: ExtruderParameters,
    dcid: DCID,
    dcm: DCM,
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
        yield from sup.pilatus("return-to-normal", None)
    elif parameters.detector_name == "eiger":
        yield from sup.eiger("return-to-normal", None, dcm)
        SSX_LOGGER.debug(f"{parameters.filename}_{caget(pv.eiger_seqID)}")
    SSX_LOGGER.debug("End of Run")
    SSX_LOGGER.info("Close hutch shutter")
    yield from bps.abs_set(shutter, ShutterDemand.CLOSE, wait=True)

    dcid.notify_end()


@log_on_entry
def collection_complete_plan(
    collection_directory: Path, detector_name: str, dcid: DCID
) -> MsgGenerator:
    if detector_name == "pilatus":
        SSX_LOGGER.info("Pilatus Acquire STOP")
        caput(pv.pilat_acquire, 0)
    elif detector_name == "eiger":
        SSX_LOGGER.info("Eiger Acquire STOP")
        caput(pv.eiger_acquire, 0)
        caput(pv.eiger_ODcapture, "Done")

    yield from bps.sleep(0.5)

    end_time = datetime.now()
    dcid.collection_complete(end_time, aborted=False)
    SSX_LOGGER.info(f"End Time = {end_time.ctime()}")

    yield from bps.null()


def run_extruder_plan(
    zebra: Zebra = inject("zebra"),
    aperture: Aperture = inject("aperture"),
    backlight: DualBacklight = inject("backlight"),
    beamstop: Beamstop = inject("beamstop"),
    detector_stage: DetectorMotion = inject("detector_motion"),
    shutter: HutchShutter = inject("shutter"),
    dcm: DCM = inject("dcm"),
    mirrors: FocusMirrorsMode = inject("focus_mirrors"),
    attenuator: ReadOnlyAttenuator = inject("attenuator"),
) -> MsgGenerator:
    start_time = datetime.now()
    SSX_LOGGER.info(f"Collection start time: {start_time.ctime()}")

    parameters: ExtruderParameters = yield from read_parameters(
        detector_stage, attenuator
    )
    # Create collection directory
    parameters.collection_directory.mkdir(parents=True, exist_ok=True)

    beam_center_device = sup.get_beam_center_device(parameters.detector_name)

    # DCID - not generated yet
    dcid = DCID(emit_errors=False, expt_params=parameters)

    yield from bpp.contingency_wrapper(
        main_extruder_plan(
            zebra=zebra,
            aperture=aperture,
            backlight=backlight,
            beamstop=beamstop,
            detector_stage=detector_stage,
            shutter=shutter,
            dcm=dcm,
            mirrors=mirrors,
            beam_center_device=beam_center_device,
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
            yield from tidy_up_at_collection_end_plan(
                zebra, shutter, parameters, dcid, dcm
            )
        ),
        auto_raise=False,
    )
