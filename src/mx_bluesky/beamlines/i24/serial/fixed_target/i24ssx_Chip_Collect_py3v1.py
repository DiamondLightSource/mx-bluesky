"""
Fixed target data collection
"""

import logging
import shutil
import time
from datetime import datetime
from pathlib import Path
from time import sleep

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy as np
from blueapi.core import MsgGenerator
from dodal.common import inject
from dodal.devices.hutch_shutter import HutchShutter, ShutterDemand
from dodal.devices.i24.aperture import Aperture
from dodal.devices.i24.beamstop import Beamstop
from dodal.devices.i24.dcm import DCM
from dodal.devices.i24.dual_backlight import DualBacklight
from dodal.devices.i24.i24_detector_motion import DetectorMotion
from dodal.devices.i24.pmac import PMAC
from dodal.devices.zebra import Zebra

from mx_bluesky.beamlines.i24.serial import log
from mx_bluesky.beamlines.i24.serial.dcid import DCID
from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import (
    ChipType,
    MappingType,
    PumpProbeSetting,
)
from mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1 import (
    write_parameter_file,
)
from mx_bluesky.beamlines.i24.serial.parameters import (
    ChipDescription,
    FixedTargetParameters,
    SSXType,
)
from mx_bluesky.beamlines.i24.serial.parameters.constants import (
    LITEMAP_PATH,
    PARAM_FILE_NAME,
    PARAM_FILE_PATH_FT,
)
from mx_bluesky.beamlines.i24.serial.setup_beamline import caget, cagetstring, caput, pv
from mx_bluesky.beamlines.i24.serial.setup_beamline import setup_beamline as sup
from mx_bluesky.beamlines.i24.serial.setup_beamline.setup_zebra_plans import (
    SHUTTER_OPEN_TIME,
    arm_zebra,
    close_fast_shutter,
    open_fast_shutter,
    open_fast_shutter_at_each_position_plan,
    reset_zebra_when_collection_done_plan,
    setup_zebra_for_fastchip_plan,
)
from mx_bluesky.beamlines.i24.serial.write_nexus import call_nexgen

ABORTED = False

logger = logging.getLogger("I24ssx.fixed_target")


def setup_logging():
    # Log should now change name daily
    logfile = time.strftime("i24fixedtarget_%d%B%y.log").lower()
    log.config(logfile)


def _create_directory_for_eiger_collection(filepath: str):
    logger.debug(f"Creating the directory for the collection in {filepath}.")
    Path(filepath).mkdir(parents=True)


def calculate_collection_timeout(parameters: FixedTargetParameters) -> float:
    """Give an estimation of the time the plan should wait for the data collection \
        to be finished.

    For non-pump probe collections and collection with short delays, it should be \
    enough to use the collection time plus a genereous 30s buffer.
    For EAVA (Excite and visit again) collections instead, the laser dwell and laser \
    delay times should be included in the calculation. For long dalays between pump \
    and probe, the shutter opening time will also need to be taken into account.
    For more details on the dynamics see
    https://confluence.diamond.ac.uk/display/MXTech/Dynamics+and+fixed+targets.

    Args:
        parameters (FixedTargerParameters): The collection parameters.

    Returns:
        The estimated collection time, in s.
    """
    pmac_move_time = 0.008  # around 7-8ms
    buffer = pmac_move_time * parameters.total_num_images + 2
    # buffer = 30
    pump_setting = parameters.pump_repeat
    collection_time = parameters.total_num_images * parameters.exposure_time_s
    if pump_setting in [
        PumpProbeSetting.NoPP,
        PumpProbeSetting.Short1,
        PumpProbeSetting.Short2,
    ]:
        timeout = collection_time + buffer
    else:
        # EAVA: Excite and visit again
        num_windows = parameters.total_num_images / parameters.num_exposures
        timeout = (
            collection_time
            + parameters.laser_dwell_s * num_windows  # type: ignore
            + parameters.laser_delay_s
            + buffer
        )
        if pump_setting == PumpProbeSetting.Medium1:
            # Long delay between pump and probe, with fast shutter opening and closing.
            timeout = timeout + SHUTTER_OPEN_TIME
    return timeout


def copy_files_to_data_location(
    dest_dir: Path | str,
    param_path: Path = PARAM_FILE_PATH_FT,
    map_file: Path = LITEMAP_PATH,
    map_type: MappingType = MappingType.Lite,
):
    if not isinstance(dest_dir, Path):
        dest_dir = Path(dest_dir)
    shutil.copy2(param_path / "parameters.txt", dest_dir / "parameters.txt")
    if map_type == MappingType.Lite:
        shutil.copy2(map_file / "currentchip.map", dest_dir / "currentchip.map")


def write_userlog(
    parameters: FixedTargetParameters,
    filename: str,
    transmission: float,
    wavelength: float,
):
    # Write a record of what was collected to the processing directory
    userlog_path = Path(parameters.visit) / f"processing/{parameters.directory}"
    userlog_fid = f"{filename}_parameters.txt"
    logger.debug(f"Write a user log in {userlog_path}")

    userlog_path.mkdir(parents=True, exist_ok=True)

    text = f"""
        Fixed Target Data Collection Parameters\n
        Data directory \t{parameters.collection_directory.as_posix()}\n
        Filename \t{filename}\n
        Shots per pos \t{parameters.num_exposures}\n
        Total N images \t{parameters.total_num_images}\n
        Exposure time \t{parameters.exposure_time_s}\n
        Det distance \t{parameters.detector_distance_mm}\n
        Transmission \t{transmission}\n
        Wavelength \t{wavelength}\n
        Detector type \t{parameters.detector_name}\n
        Pump status \t{parameters.pump_repeat}\n
        Pump exp time \t{parameters.laser_dwell_s}\n
        Pump delay \t{parameters.laser_delay_s}\n
    """
    with open(userlog_path / userlog_fid, "w") as f:
        f.write(text)


@log.log_on_entry
def get_chip_prog_values(
    parameters: FixedTargetParameters,
):
    # this is where p variables for fast laser expts will be set
    if parameters.pump_repeat in [
        PumpProbeSetting.NoPP,
        PumpProbeSetting.Short1,
        PumpProbeSetting.Short2,
        PumpProbeSetting.Medium1,
    ]:
        pump_repeat_pvar = 0
    elif parameters.pump_repeat == PumpProbeSetting.Repeat1:
        pump_repeat_pvar = 1
    elif parameters.pump_repeat == PumpProbeSetting.Repeat2:
        pump_repeat_pvar = 2
    elif parameters.pump_repeat == PumpProbeSetting.Repeat3:
        pump_repeat_pvar = 3
    elif parameters.pump_repeat == PumpProbeSetting.Repeat5:
        pump_repeat_pvar = 5
    elif parameters.pump_repeat == PumpProbeSetting.Repeat10:
        pump_repeat_pvar = 10
    else:
        raise ValueError(f"Unknown pump_repeat, pump_repeat = {parameters.pump_repeat}")

    logger.info(
        f"Pump repeat is {str(parameters.pump_repeat)}, PVAR set to {pump_repeat_pvar}"
    )

    if parameters.pump_repeat == PumpProbeSetting.Short2:
        pump_in_probe = 1
    else:
        pump_in_probe = 0

    logger.info(f"pump_in_probe set to {pump_in_probe}")

    chip_dict: dict[str, list] = {
        "X_NUM_STEPS": [11, parameters.chip.x_num_steps],
        "Y_NUM_STEPS": [12, parameters.chip.y_num_steps],
        "X_STEP_SIZE": [13, parameters.chip.x_step_size],
        "Y_STEP_SIZE": [14, parameters.chip.y_step_size],
        "DWELL_TIME": [15, parameters.exposure_time_s],
        "X_START": [16, 0],
        "Y_START": [17, 0],
        "Z_START": [18, 0],
        "X_NUM_BLOCKS": [20, parameters.chip.x_blocks],
        "Y_NUM_BLOCKS": [21, parameters.chip.y_blocks],
        "X_BLOCK_SIZE": [24, parameters.chip.x_block_size],
        "Y_BLOCK_SIZE": [25, parameters.chip.y_block_size],
        "COLTYPE": [26, 41],
        "N_EXPOSURES": [30, parameters.num_exposures],
        "PUMP_REPEAT": [32, pump_repeat_pvar],
        "LASER_DWELL": [34, parameters.laser_dwell_s],
        "LASERTWO_DWELL": [35, parameters.pre_pump_exposure_s],
        "LASER_DELAY": [37, parameters.laser_delay_s],
        "PUMP_IN_PROBE": [38, pump_in_probe],
    }

    chip_dict["DWELL_TIME"][1] = 1000 * parameters.exposure_time_s
    chip_dict["LASER_DWELL"][1] = (
        1000 * parameters.laser_dwell_s if parameters.laser_dwell_s else 0
    )
    chip_dict["LASERTWO_DWELL"][1] = (
        1000 * parameters.pre_pump_exposure_s if parameters.pre_pump_exposure_s else 0
    )
    chip_dict["LASER_DELAY"][1] = (
        1000 * parameters.laser_delay_s if parameters.laser_delay_s else 0
    )

    return chip_dict


@log.log_on_entry
def load_motion_program_data(
    pmac: PMAC,
    motion_program_dict: dict[str, list],
    map_type: int,
    pump_repeat: int,
    checker_pattern: bool,
):
    logger.info("Loading motion program data for chip.")
    logger.info(f"Pump_repeat is {PumpProbeSetting(pump_repeat)}")
    if pump_repeat == PumpProbeSetting.NoPP:
        if map_type == MappingType.NoMap:
            prefix = 11
            logger.info(f"Map type is None, setting program prefix to {prefix}")
        elif map_type == MappingType.Lite:
            prefix = 12
        elif map_type == MappingType.Full:
            prefix = 13
        else:
            logger.warning(f"Unknown Map Type, map_type = {map_type}")
            return
    elif pump_repeat in [pp.value for pp in PumpProbeSetting if pp != 0]:
        # Pump setting chosen
        prefix = 14
        logger.info(f"Setting program prefix to {prefix}")
        yield from bps.abs_set(pmac.pmac_string, "P1439=0", wait=True)
        if checker_pattern:
            logger.info("Checker pattern setting enabled.")
            yield from bps.abs_set(pmac.pmac_string, "P1439=1", wait=True)
        if pump_repeat == PumpProbeSetting.Medium1:
            # Medium1 has time delays (Fast shutter opening time in ms)
            yield from bps.abs_set(pmac.pmac_string, "P1441=50", wait=True)
        else:
            yield from bps.abs_set(pmac.pmac_string, "P1441=0", wait=True)
    else:
        logger.warning(f"Unknown Pump repeat, pump_repeat = {pump_repeat}")
        return

    logger.info("Set PMAC_STRING pv.")
    for key in sorted(motion_program_dict.keys()):
        v = motion_program_dict[key]
        pvar_base = prefix * 100
        pvar = pvar_base + v[0]
        value = str(v[1])
        s = f"P{pvar}={value}"
        logger.info(f"{key} \t {s}")
        yield from bps.abs_set(pmac.pmac_string, s, wait=True)
        yield from bps.sleep(0.02)
    yield from bps.sleep(0.2)


@log.log_on_entry
def get_prog_num(
    chip_type: ChipType, map_type: MappingType, pump_repeat: PumpProbeSetting
) -> int:
    """Get the motion program number based on the experiment parameters set by \
    the user.
    Any pump probe experiment will return program number 14 (assumes lite mapping).
    For non pump probe experiments, the program number depends on the chip and map type:
        - Custom, Mini and PSI chips, as well as Oxford chips with no map return 11
        - Oxford chips with lite mapping return 12
        - Oxford chips with full mapping should return 13. Currently disabled, will \
            raise an error.
    """
    logger.info("Get Program Number for the motion program.")
    logger.info(f"Pump_repeat: {str(pump_repeat)} \t Chip Type: {str(chip_type)}")
    if pump_repeat != PumpProbeSetting.NoPP:
        logger.info("Assuming Map type = Mapping Lite.")
        logger.info("Program number: 14")
        return 14

    if chip_type not in [ChipType.Oxford, ChipType.OxfordInner]:
        logger.info("Program number: 11")
        return 11

    if map_type == MappingType.NoMap:
        logger.info(f"Map type: {str(map_type)}")
        logger.info("Program number: 11")
        return 11
    if map_type == MappingType.Lite:
        logger.info(f"Map type: {str(map_type)}")
        logger.info("Program number: 12")
        return 12
    if map_type == MappingType.Full:
        # TODO See https://github.com/DiamondLightSource/mx-bluesky/issues/515
        logger.info(f"Map type: {str(map_type)}")
        logger.info("Program number: 13")
        # TODO once reinstated return 13
        msg = "Full mapping is broken and currently disabled."
        logger.error(msg)
        raise ValueError(msg)


@log.log_on_entry
def datasetsizei24(
    n_exposures: int,
    chip_params: ChipDescription,
    map_type: MappingType,
) -> int:
    # Calculates how many images will be collected based on map type and N repeats
    logger.info("Calculate total number of images expected in data collection.")

    if map_type == MappingType.NoMap:
        if chip_params.chip_type == ChipType.Custom:
            total_numb_imgs = chip_params.x_num_steps * chip_params.y_num_steps
            logger.info(
                f"Map type: None \tCustom chip \tNumber of images {total_numb_imgs}"
            )
        else:
            chip_format = chip_params.chip_format[:4]
            total_numb_imgs = int(np.prod(chip_format))
            logger.info(
                f"""Map type: None \tOxford chip {chip_params.chip_type} \t \
                    Number of images {total_numb_imgs}"""
            )

    elif map_type == MappingType.Lite:
        logger.info(f"Using Mapping Lite on chip type {chip_params.chip_type}")
        chip_format = chip_params.chip_format[2:4]
        block_count = 0
        with open(LITEMAP_PATH / "currentchip.map") as f:
            for line in f.readlines():
                entry = line.split()
                if entry[2] == "1":
                    block_count += 1

        logger.info(f"Block count={block_count}")
        logger.info(f"Chip format={chip_format}")

        logger.info(f"Number of exposures={n_exposures}")

        total_numb_imgs = int(np.prod(chip_format) * block_count * n_exposures)
        logger.info(f"Calculated number of images: {total_numb_imgs}")

    elif map_type == MappingType.Full:
        logger.error("Not Set Up For Full Mapping")
        raise ValueError("The beamline is currently not set for Full Mapping.")

    else:
        logger.warning(f"Unknown Map Type, map_type = {str(map_type)}")
        raise ValueError("Unknown map type")

    logger.info("Set PV to calculated number of images.")
    caput(pv.me14e_gp10, int(total_numb_imgs))

    return int(total_numb_imgs)


@log.log_on_entry
def start_i24(
    zebra: Zebra,
    aperture: Aperture,
    backlight: DualBacklight,
    beamstop: Beamstop,
    detector_stage: DetectorMotion,
    shutter: HutchShutter,
    parameters: FixedTargetParameters,
    dcid: DCID,
):
    """Set up for I24 fixed target data collection, trigger the detector and open \
    the hutch shutter.
    Returns the start_time.
    """

    logger.info("Start I24 data collection.")
    start_time = datetime.now()
    logger.info(f"Collection start time {start_time.ctime()}")

    logger.debug("Set up beamline")
    yield from sup.setup_beamline_for_collection_plan(
        aperture, backlight, beamstop, wait=True
    )

    yield from sup.move_detector_stage_to_position_plan(
        detector_stage, parameters.detector_distance_mm
    )

    logger.debug("Set up beamline DONE")

    filepath = parameters.collection_directory.as_posix()
    filename = parameters.filename

    logger.debug("Acquire Region")

    num_gates = parameters.total_num_images // parameters.num_exposures

    logger.info(f"Total number of images: {parameters.total_num_images}")
    logger.info(f"Number of exposures: {parameters.num_exposures}")
    logger.info(f"Number of gates (=Total images/N exposures): {num_gates:.4f}")

    if parameters.detector_name == "pilatus":
        logger.info("Using Pilatus detector")
        logger.info(f"Fastchip Pilatus setup: filepath {filepath}")
        logger.info(f"Fastchip Pilatus setup: filename {filename}")
        logger.info(
            f"Fastchip Pilatus setup: number of images {parameters.total_num_images}"
        )
        logger.info(
            f"Fastchip Pilatus setup: exposure time {parameters.exposure_time_s}"
        )

        sup.pilatus(
            "fastchip",
            [
                filepath,
                filename,
                parameters.total_num_images,
                parameters.exposure_time_s,
            ],
        )

        # DCID process depends on detector PVs being set up already
        logger.debug("Start DCID process")
        dcid.generate_dcid(
            visit=parameters.visit.name,
            image_dir=filepath,
            start_time=start_time,
            num_images=parameters.total_num_images,
            exposure_time=parameters.exposure_time_s,
            shots_per_position=parameters.num_exposures,
            pump_exposure_time=parameters.laser_dwell_s,
            pump_delay=parameters.laser_delay_s or 0,
            pump_status=parameters.pump_repeat.value,
        )

        logger.debug("Arm Pilatus. Arm Zebra.")
        shutter_time_offset = SHUTTER_OPEN_TIME if PumpProbeSetting.Medium1 else 0.0
        yield from setup_zebra_for_fastchip_plan(
            zebra,
            parameters.detector_name,
            num_gates,
            parameters.num_exposures,
            parameters.exposure_time_s,
            shutter_time_offset,
            wait=True,
        )
        if parameters.pump_repeat == PumpProbeSetting.Medium1:
            yield from open_fast_shutter_at_each_position_plan(
                zebra, parameters.num_exposures, parameters.exposure_time_s
            )
        caput(pv.pilat_acquire, "1")  # Arm pilatus
        yield from arm_zebra(zebra)
        caput(pv.pilat_filename, filename)
        sleep(1.5)

    elif parameters.detector_name == "eiger":
        logger.info("Using Eiger detector")

        _create_directory_for_eiger_collection(filepath)

        logger.info(f"Triggered Eiger setup: filepath {filepath}")
        logger.info(f"Triggered Eiger setup: filename {filename}")
        logger.info(
            f"Triggered Eiger setup: number of images {parameters.total_num_images}"
        )
        logger.info(
            f"Triggered Eiger setup: exposure time {parameters.exposure_time_s}"
        )

        sup.eiger(
            "triggered",
            [
                filepath,
                filename,
                parameters.total_num_images,
                parameters.exposure_time_s,
            ],
        )

        # DCID process depends on detector PVs being set up already
        logger.debug("Start DCID process")
        dcid.generate_dcid(
            visit=parameters.visit.name,
            image_dir=filepath,
            start_time=start_time,
            num_images=parameters.total_num_images,
            exposure_time=parameters.exposure_time_s,
            shots_per_position=parameters.num_exposures,
            pump_exposure_time=parameters.laser_dwell_s,
            pump_delay=parameters.laser_delay_s or 0,
            pump_status=parameters.pump_repeat.value,
        )

        logger.debug("Arm Zebra.")
        shutter_time_offset = SHUTTER_OPEN_TIME if PumpProbeSetting.Medium1 else 0.0
        yield from setup_zebra_for_fastchip_plan(
            zebra,
            parameters.detector_name,
            num_gates,
            parameters.num_exposures,
            parameters.exposure_time_s,
            shutter_time_offset,
            wait=True,
        )
        if parameters.pump_repeat == PumpProbeSetting.Medium1:
            yield from open_fast_shutter_at_each_position_plan(
                zebra, parameters.num_exposures, parameters.exposure_time_s
            )
        yield from arm_zebra(zebra)

        sleep(1.5)

    else:
        msg = f"Unknown Detector Type, det_type = {parameters.detector_name}"
        logger.error(msg)
        raise ValueError(msg)

    # Open the hutch shutter
    yield from bps.abs_set(shutter, ShutterDemand.OPEN, wait=True)

    return start_time


@log.log_on_entry
def finish_i24(
    zebra: Zebra,
    pmac: PMAC,
    shutter: HutchShutter,
    dcm: DCM,
    parameters: FixedTargetParameters,
):
    logger.info(f"Finish I24 data collection with {parameters.detector_name} detector.")

    complete_filename: str
    transmission = float(caget(pv.pilat_filtertrasm))
    wavelength = yield from bps.rd(dcm.wavelength_in_a)

    if parameters.detector_name == "pilatus":
        logger.debug("Finish I24 Pilatus")
        complete_filename = f"{parameters.filename}_{caget(pv.pilat_filenum)}"
        yield from reset_zebra_when_collection_done_plan(zebra)
        sup.pilatus("return-to-normal", None)
        sleep(0.2)
    elif parameters.detector_name == "eiger":
        logger.debug("Finish I24 Eiger")
        yield from reset_zebra_when_collection_done_plan(zebra)
        sup.eiger("return-to-normal", None)
        complete_filename = cagetstring(pv.eiger_ODfilenameRBV)  # type: ignore
    else:
        raise ValueError(f"{parameters.detector_name=} unrecognised")

    # Detector independent moves
    logger.info("Move chip back to home position by setting PMAC_STRING pv.")
    yield from bps.trigger(pmac.to_xyz_zero)
    logger.info("Closing shutter")
    yield from bps.abs_set(shutter, ShutterDemand.CLOSE, wait=True)

    # Write a record of what was collected to the processing directory
    write_userlog(parameters, complete_filename, transmission, wavelength)


def run_aborted_plan(pmac: PMAC, dcid: DCID):
    """Plan to send pmac_strings to tell the PMAC when a collection has been aborted, \
        either by pressing the Abort button or because of a timeout, and to reset the \
        P variable.
    """
    logger.warning("Data Collection Aborted")
    yield from bps.trigger(pmac.abort_program, wait=True)

    end_time = datetime.now()
    dcid.collection_complete(end_time, aborted=True)


@log.log_on_entry
def main_fixed_target_plan(
    zebra: Zebra,
    pmac: PMAC,
    aperture: Aperture,
    backlight: DualBacklight,
    beamstop: Beamstop,
    detector_stage: DetectorMotion,
    shutter: HutchShutter,
    dcm: DCM,
    parameters: FixedTargetParameters,
    dcid: DCID,
) -> MsgGenerator:
    logger.info("Running a chip collection on I24")

    logger.info("Getting Program Dictionary")

    # If alignment type is Oxford inner it is still an Oxford type chip
    if parameters.chip.chip_type == ChipType.OxfordInner:
        logger.debug("Change chip type Oxford Inner to Oxford.")
        parameters.chip.chip_type = ChipType.Oxford

    chip_prog_dict = get_chip_prog_values(parameters)
    logger.info("Loading Motion Program Data")
    yield from load_motion_program_data(
        pmac,
        chip_prog_dict,
        parameters.map_type,
        parameters.pump_repeat,
        parameters.checker_pattern,
    )

    parameters.total_num_images = datasetsizei24(
        parameters.num_exposures, parameters.chip, parameters.map_type
    )

    start_time = yield from start_i24(
        zebra, aperture, backlight, beamstop, detector_stage, shutter, parameters, dcid
    )

    logger.info("Moving to Start")
    yield from bps.trigger(pmac.to_xyz_zero)
    sleep(2.0)

    # Now ready for data collection. Open fast shutter (zebra gate)
    logger.info("Opening fast shutter.")
    yield from open_fast_shutter(zebra)

    # Kick off the StartOfCollect script
    logger.debug("Notify DCID of the start of the collection.")
    dcid.notify_start()

    wavelength = yield from bps.rd(dcm.wavelength_in_a)
    if parameters.detector_name == "eiger":
        logger.debug("Start nexus writing service.")
        call_nexgen(
            chip_prog_dict,
            start_time,
            parameters,
            wavelength,
        )

    yield from kickoff_and_complete_collection(pmac, parameters)


def kickoff_and_complete_collection(pmac: PMAC, parameters: FixedTargetParameters):
    prog_num = get_prog_num(
        parameters.chip.chip_type, parameters.map_type, parameters.pump_repeat
    )
    yield from bps.abs_set(pmac.program_number, prog_num, group="setup_pmac")
    # Calculate approx collection time
    total_collection_time = calculate_collection_timeout(parameters)
    logger.info(f"Estimated collection time: {total_collection_time}s.")
    yield from bps.abs_set(
        pmac.collection_time, total_collection_time, group="setup_pmac"
    )
    yield from bps.wait(group="setup_pmac")  # Make sure the soft signals are set

    @bpp.run_decorator(md={"subplan_name": "run_ft_collection"})
    def run_collection():
        logger.info(f"Kick off PMAC with program number {prog_num}.")
        yield from bps.kickoff(pmac.run_program, wait=True)
        yield from bps.complete(pmac.run_program, wait=True)
        logger.info("Collection completed without errors.")

    yield from run_collection()


@log.log_on_entry
def collection_complete_plan(
    dcid: DCID, collection_directory: Path, map_type: MappingType
) -> MsgGenerator:
    end_time = datetime.now()
    logger.debug(f"Collection end time {end_time}")
    dcid.collection_complete(end_time, aborted=False)

    # Copy parameter file and eventual chip map to collection directory
    copy_files_to_data_location(collection_directory, map_type=map_type)
    yield from bps.null()


@log.log_on_entry
def tidy_up_after_collection_plan(
    zebra: Zebra,
    pmac: PMAC,
    shutter: HutchShutter,
    dcm: DCM,
    parameters: FixedTargetParameters,
    dcid: DCID,
) -> MsgGenerator:
    """A plan to be run to tidy things up at the end af a fixed target collection, \
    both successful or aborted.
    """
    logger.info("Closing fast shutter")
    yield from close_fast_shutter(zebra)
    sleep(2.0)

    # This probably should go in main then
    if parameters.detector_name == "pilatus":
        logger.debug("Pilatus Acquire STOP")
        caput(pv.pilat_acquire, 0)
    elif parameters.detector_name == "eiger":
        logger.debug("Eiger Acquire STOP")
        caput(pv.eiger_acquire, 0)
        caput(pv.eiger_ODcapture, "Done")
    sleep(0.5)

    yield from finish_i24(zebra, pmac, shutter, dcm, parameters)

    logger.debug("Notify DCID of end of collection.")
    dcid.notify_end()

    logger.debug("Quick summary of settings")
    logger.debug(f"Chip name = {parameters.filename} sub_dir = {parameters.directory}")


def run_fixed_target_plan(
    zebra: Zebra = inject("zebra"),
    pmac: PMAC = inject("pmac"),
    aperture: Aperture = inject("aperture"),
    backlight: DualBacklight = inject("backlight"),
    beamstop: Beamstop = inject("beamstop"),
    detector_stage: DetectorMotion = inject("detector_motion"),
    shutter: HutchShutter = inject("shutter"),
    dcm: DCM = inject("dcm"),
) -> MsgGenerator:
    setup_logging()

    # in the first instance, write params here
    yield from write_parameter_file(detector_stage)

    logger.info("Getting parameters from file.")
    parameters = FixedTargetParameters.from_file(PARAM_FILE_PATH_FT / PARAM_FILE_NAME)

    log_msg = f"""
            Parameters for I24 serial collection: \n
                Chip name is {parameters.filename}
                visit = {parameters.visit}
                sub_dir = {parameters.directory}
                n_exposures = {parameters.num_exposures}
                chip_type = {str(parameters.chip.chip_type)}
                map_type = {str(parameters.map_type)}
                dcdetdist = {parameters.detector_distance_mm}
                exptime = {parameters.exposure_time_s}
                det_type = {parameters.detector_name}
                pump_repeat = {str(parameters.pump_repeat)}
                pumpexptime = {parameters.laser_dwell_s}
                pumpdelay = {parameters.laser_delay_s}
                prepumpexptime = {parameters.pre_pump_exposure_s}
        """
    logger.info(log_msg)

    # DCID instance - do not create yet
    dcid = DCID(
        emit_errors=False,
        ssx_type=SSXType.FIXED,
        detector=parameters.detector_name,
    )

    yield from bpp.contingency_wrapper(
        main_fixed_target_plan(
            zebra,
            pmac,
            aperture,
            backlight,
            beamstop,
            detector_stage,
            shutter,
            dcm,
            parameters,
            dcid,
        ),
        except_plan=lambda e: (yield from run_aborted_plan(pmac, dcid)),
        final_plan=lambda: (
            yield from tidy_up_after_collection_plan(
                zebra, pmac, shutter, dcm, parameters, dcid
            )
        ),
        auto_raise=False,
    )
