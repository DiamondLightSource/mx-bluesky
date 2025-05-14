"""
Fixed target data collection
"""

from datetime import datetime
from pathlib import Path
from traceback import format_exception

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
from dodal.devices.i24.pmac import PMAC
from dodal.devices.zebra.zebra import Zebra

from mx_bluesky.beamlines.i24.serial.dcid import (
    DCID,
    get_pilatus_filename_template_from_device,
    read_beam_info_from_hardware,
)
from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import (
    ChipType,
    MappingType,
    PumpProbeSetting,
)
from mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_Manager_py3v1 import (
    read_parameters,
    upload_chip_map_to_geobrick,
)
from mx_bluesky.beamlines.i24.serial.log import SSX_LOGGER, log_on_entry
from mx_bluesky.beamlines.i24.serial.parameters import FixedTargetParameters
from mx_bluesky.beamlines.i24.serial.parameters.constants import BEAM_CENTER_LUT_FILES
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


def write_userlog(
    parameters: FixedTargetParameters,
    filename: str,
    transmission: float,
    wavelength: float,
):
    # Write a record of what was collected to the processing directory
    userlog_path = Path(parameters.visit) / f"processing/{parameters.directory}"
    userlog_fid = f"{filename}_parameters.txt"
    SSX_LOGGER.debug(f"Write a user log in {userlog_path}")

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


@log_on_entry
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

    SSX_LOGGER.info(
        f"Pump repeat is {str(parameters.pump_repeat)}, PVAR set to {pump_repeat_pvar}"
    )

    if parameters.pump_repeat == PumpProbeSetting.Short2:
        pump_in_probe = 1
    else:
        pump_in_probe = 0

    SSX_LOGGER.info(f"pump_in_probe set to {pump_in_probe}")

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


@log_on_entry
def load_motion_program_data(
    pmac: PMAC,
    motion_program_dict: dict[str, list],
    map_type: int,
    pump_repeat: int,
    checker_pattern: bool,
):
    SSX_LOGGER.info("Loading motion program data for chip.")
    SSX_LOGGER.info(f"Pump_repeat is {PumpProbeSetting(pump_repeat)}")
    if pump_repeat == PumpProbeSetting.NoPP:
        if map_type == MappingType.NoMap:
            prefix = 11
            SSX_LOGGER.info(f"Map type is None, setting program prefix to {prefix}")
        elif map_type == MappingType.Lite:
            prefix = 12
        else:
            SSX_LOGGER.warning(f"Unknown Map Type, map_type = {map_type}")
            return
    elif pump_repeat in [pp.value for pp in PumpProbeSetting if pp != 0]:
        # Pump setting chosen
        prefix = 14
        SSX_LOGGER.info(f"Setting program prefix to {prefix}")
        yield from bps.abs_set(pmac.pmac_string, "P1439=0", wait=True)
        if checker_pattern:
            SSX_LOGGER.info("Checker pattern setting enabled.")
            yield from bps.abs_set(pmac.pmac_string, "P1439=1", wait=True)
        if pump_repeat == PumpProbeSetting.Medium1:
            # Medium1 has time delays (Fast shutter opening time in ms)
            yield from bps.abs_set(pmac.pmac_string, "P1441=50", wait=True)
        else:
            yield from bps.abs_set(pmac.pmac_string, "P1441=0", wait=True)
    else:
        SSX_LOGGER.warning(f"Unknown Pump repeat, pump_repeat = {pump_repeat}")
        return

    SSX_LOGGER.info("Set PMAC_STRING pv.")
    for key in sorted(motion_program_dict.keys()):
        v = motion_program_dict[key]
        pvar_base = prefix * 100
        pvar = pvar_base + v[0]
        value = str(v[1])
        s = f"P{pvar}={value}"
        SSX_LOGGER.info(f"{key} \t {s}")
        yield from bps.abs_set(pmac.pmac_string, s, wait=True)
        yield from bps.sleep(0.02)
    yield from bps.sleep(0.2)


@log_on_entry
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
    SSX_LOGGER.info("Get Program Number for the motion program.")
    SSX_LOGGER.info(f"Pump_repeat: {str(pump_repeat)} \t Chip Type: {str(chip_type)}")
    if pump_repeat != PumpProbeSetting.NoPP:
        SSX_LOGGER.info("Assuming Map type = Mapping Lite.")
        SSX_LOGGER.info("Program number: 14")
        return 14

    if chip_type not in [ChipType.Oxford, ChipType.OxfordInner]:
        SSX_LOGGER.info("Program number: 11")
        return 11

    if map_type == MappingType.NoMap:
        SSX_LOGGER.info(f"Map type: {str(map_type)}")
        SSX_LOGGER.info("Program number: 11")
        return 11
    if map_type == MappingType.Lite:
        SSX_LOGGER.info(f"Map type: {str(map_type)}")
        SSX_LOGGER.info("Program number: 12")
        return 12


@log_on_entry
def set_datasize(
    parameters: FixedTargetParameters,
):
    SSX_LOGGER.info(
        f"Setting PV to calculated total number of images: {parameters.total_num_images}"
    )

    SSX_LOGGER.debug(f"Map type: {parameters.map_type}")
    SSX_LOGGER.debug(f"Chip type: {parameters.chip.chip_type}")
    if parameters.map_type == MappingType.Lite:
        SSX_LOGGER.debug(f"Num exposures: {parameters.num_exposures}")
        SSX_LOGGER.debug(f"Block count: {len(parameters.chip_map)}")

    caput(pv.me14e_gp10, parameters.total_num_images)


@log_on_entry
def start_i24(
    zebra: Zebra,
    aperture: Aperture,
    backlight: DualBacklight,
    beamstop: Beamstop,
    detector_stage: DetectorMotion,
    shutter: HutchShutter,
    parameters: FixedTargetParameters,
    dcm: DCM,
    mirrors: FocusMirrorsMode,
    beam_center_device: DetectorBeamCenter,
    dcid: DCID,
):
    """Set up for I24 fixed target data collection, trigger the detector and open \
    the hutch shutter.
    Returns the start_time.
    """

    beam_settings = yield from read_beam_info_from_hardware(
        dcm, mirrors, beam_center_device, parameters.detector_name
    )
    SSX_LOGGER.info("Start I24 data collection.")
    start_time = datetime.now()
    SSX_LOGGER.info(f"Collection start time {start_time.ctime()}")

    SSX_LOGGER.debug("Set up beamline")
    yield from sup.setup_beamline_for_collection_plan(
        aperture, backlight, beamstop, wait=True
    )

    yield from sup.move_detector_stage_to_position_plan(
        detector_stage, parameters.detector_distance_mm
    )

    SSX_LOGGER.debug("Set up beamline DONE")

    filepath = parameters.collection_directory.as_posix()
    filename = parameters.filename

    SSX_LOGGER.debug("Acquire Region")

    num_gates = parameters.total_num_images // parameters.num_exposures

    SSX_LOGGER.info(f"Total number of images: {parameters.total_num_images}")
    SSX_LOGGER.info(f"Number of exposures: {parameters.num_exposures}")
    SSX_LOGGER.info(f"Number of gates (=Total images/N exposures): {num_gates:.4f}")

    if parameters.detector_name == "pilatus":
        SSX_LOGGER.info("Using Pilatus detector")
        SSX_LOGGER.info(f"Fastchip Pilatus setup: filepath {filepath}")
        SSX_LOGGER.info(f"Fastchip Pilatus setup: filename {filename}")
        SSX_LOGGER.info(
            f"Fastchip Pilatus setup: number of images {parameters.total_num_images}"
        )
        SSX_LOGGER.info(
            f"Fastchip Pilatus setup: exposure time {parameters.exposure_time_s}"
        )

        yield from sup.pilatus(
            "fastchip",
            [
                filepath,
                filename,
                parameters.total_num_images,
                parameters.exposure_time_s,
            ],
        )

        # DCID process depends on detector PVs being set up already
        SSX_LOGGER.debug("Start DCID process")
        filetemplate = yield from get_pilatus_filename_template_from_device()
        dcid.generate_dcid(
            beam_settings=beam_settings,
            image_dir=filepath,
            file_template=filetemplate,
            num_images=parameters.total_num_images,
            shots_per_position=parameters.num_exposures,
            start_time=start_time,
            pump_probe=bool(parameters.pump_repeat),
        )

        SSX_LOGGER.debug("Arm Pilatus. Arm Zebra.")
        shutter_time_offset = (
            SHUTTER_OPEN_TIME
            if parameters.pump_repeat is PumpProbeSetting.Medium1
            else 0.0
        )
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
        yield from bps.sleep(1.5)

    elif parameters.detector_name == "eiger":
        SSX_LOGGER.info("Using Eiger detector")

        SSX_LOGGER.debug(f"Creating the directory for the collection in {filepath}.")

        SSX_LOGGER.info(f"Triggered Eiger setup: filepath {filepath}")
        SSX_LOGGER.info(f"Triggered Eiger setup: filename {filename}")
        SSX_LOGGER.info(
            f"Triggered Eiger setup: number of images {parameters.total_num_images}"
        )
        SSX_LOGGER.info(
            f"Triggered Eiger setup: exposure time {parameters.exposure_time_s}"
        )

        yield from sup.eiger(
            "triggered",
            [
                filepath,
                filename,
                parameters.total_num_images,
                parameters.exposure_time_s,
            ],
            dcm,
        )

        # DCID process depends on detector PVs being set up already
        SSX_LOGGER.debug("Start DCID process")
        complete_filename = cagetstring(pv.eiger_ODfilenameRBV)
        filetemplate = f"{complete_filename}.nxs"
        dcid.generate_dcid(
            beam_settings=beam_settings,
            image_dir=filepath,
            file_template=filetemplate,
            num_images=parameters.total_num_images,
            shots_per_position=parameters.num_exposures,
            start_time=start_time,
            pump_probe=bool(parameters.pump_repeat),
        )

        SSX_LOGGER.debug("Arm Zebra.")
        shutter_time_offset = (
            SHUTTER_OPEN_TIME
            if parameters.pump_repeat is PumpProbeSetting.Medium1
            else 0.0
        )
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

        yield from bps.sleep(1.5)

    else:
        msg = f"Unknown Detector Type, det_type = {parameters.detector_name}"
        SSX_LOGGER.error(msg)
        raise ValueError(msg)

    # Open the hutch shutter
    yield from bps.abs_set(shutter, ShutterDemand.OPEN, wait=True)

    return start_time


@log_on_entry
def finish_i24(
    zebra: Zebra,
    pmac: PMAC,
    shutter: HutchShutter,
    dcm: DCM,
    parameters: FixedTargetParameters,
):
    SSX_LOGGER.info(
        f"Finish I24 data collection with {parameters.detector_name} detector."
    )

    complete_filename: str
    transmission = float(caget(pv.pilat_filtertrasm))
    wavelength = yield from bps.rd(dcm.wavelength_in_a)

    if parameters.detector_name == "pilatus":
        SSX_LOGGER.debug("Finish I24 Pilatus")
        complete_filename = f"{parameters.filename}_{caget(pv.pilat_filenum)}"
        yield from reset_zebra_when_collection_done_plan(zebra)
        yield from sup.pilatus("return-to-normal", None)
        yield from bps.sleep(0.2)
    elif parameters.detector_name == "eiger":
        SSX_LOGGER.debug("Finish I24 Eiger")
        yield from reset_zebra_when_collection_done_plan(zebra)
        yield from sup.eiger("return-to-normal", None, dcm)
        complete_filename = cagetstring(pv.eiger_ODfilenameRBV)  # type: ignore
    else:
        raise ValueError(f"{parameters.detector_name=} unrecognised")

    # Detector independent moves
    SSX_LOGGER.info("Move chip back to home position by setting PMAC_STRING pv.")
    yield from bps.trigger(pmac.to_xyz_zero)
    SSX_LOGGER.info("Closing shutter")
    yield from bps.abs_set(shutter, ShutterDemand.CLOSE, wait=True)

    # Write a record of what was collected to the processing directory
    write_userlog(parameters, complete_filename, transmission, wavelength)


def run_aborted_plan(pmac: PMAC, dcid: DCID, exception: Exception):
    """Plan to send pmac_strings to tell the PMAC when a collection has been aborted, \
        either by pressing the Abort button or because of a timeout, and to reset the \
        P variable.
    """
    SSX_LOGGER.warning(f"Data Collection Aborted: {format_exception(exception)}")
    yield from bps.trigger(pmac.abort_program, wait=True)

    end_time = datetime.now()
    dcid.collection_complete(end_time, aborted=True)


@log_on_entry
def main_fixed_target_plan(
    zebra: Zebra,
    pmac: PMAC,
    aperture: Aperture,
    backlight: DualBacklight,
    beamstop: Beamstop,
    detector_stage: DetectorMotion,
    shutter: HutchShutter,
    dcm: DCM,
    mirrors: FocusMirrorsMode,
    beam_center_device: DetectorBeamCenter,
    parameters: FixedTargetParameters,
    dcid: DCID,
) -> MsgGenerator:
    SSX_LOGGER.info("Running a chip collection on I24")

    beam_center_pixels = sup.compute_beam_center_position_from_lut(
        BEAM_CENTER_LUT_FILES[parameters.detector_name],
        parameters.detector_distance_mm,
        parameters.detector_size_constants,
    )
    yield from sup.set_detector_beam_center_plan(
        beam_center_device,
        beam_center_pixels,
    )

    SSX_LOGGER.info("Getting Program Dictionary")

    # If alignment type is Oxford inner it is still an Oxford type chip
    if parameters.chip.chip_type == ChipType.OxfordInner:
        SSX_LOGGER.debug("Change chip type Oxford Inner to Oxford.")
        parameters.chip.chip_type = ChipType.Oxford

    chip_prog_dict = get_chip_prog_values(parameters)
    SSX_LOGGER.info("Loading Motion Program Data")
    yield from load_motion_program_data(
        pmac,
        chip_prog_dict,
        parameters.map_type,
        parameters.pump_repeat,
        parameters.checker_pattern,
    )

    set_datasize(parameters)

    start_time = yield from start_i24(
        zebra,
        aperture,
        backlight,
        beamstop,
        detector_stage,
        shutter,
        parameters,
        dcm,
        mirrors,
        beam_center_device,
        dcid,
    )

    SSX_LOGGER.info("Moving to Start")
    yield from bps.trigger(pmac.to_xyz_zero)
    yield from bps.sleep(2.0)

    # Now ready for data collection. Open fast shutter (zebra gate)
    SSX_LOGGER.info("Opening fast shutter.")
    yield from open_fast_shutter(zebra)

    # Kick off the StartOfCollect script
    SSX_LOGGER.debug("Notify DCID of the start of the collection.")
    dcid.notify_start()

    if parameters.detector_name == "eiger":
        wavelength = yield from bps.rd(dcm.wavelength_in_a)
        beam_x = yield from bps.rd(beam_center_device.beam_x)
        beam_y = yield from bps.rd(beam_center_device.beam_y)
        SSX_LOGGER.debug("Start nexus writing service.")
        call_nexgen(
            chip_prog_dict, parameters, wavelength, (beam_x, beam_y), start_time
        )

    yield from kickoff_and_complete_collection(pmac, parameters)


def kickoff_and_complete_collection(pmac: PMAC, parameters: FixedTargetParameters):
    prog_num = get_prog_num(
        parameters.chip.chip_type, parameters.map_type, parameters.pump_repeat
    )
    yield from bps.abs_set(pmac.program_number, prog_num, group="setup_pmac")
    yield from bps.wait(group="setup_pmac")  # Make sure the soft signals are set

    @bpp.run_decorator(md={"subplan_name": "run_ft_collection"})
    def run_collection():
        SSX_LOGGER.info(f"Kick off PMAC with program number {prog_num}.")
        yield from bps.kickoff(pmac.run_program, wait=True)
        yield from bps.complete(pmac.run_program, wait=True)
        SSX_LOGGER.info("Collection completed without errors.")

    yield from run_collection()


@log_on_entry
def collection_complete_plan(
    dcid: DCID, collection_directory: Path, map_type: MappingType
) -> MsgGenerator:
    end_time = datetime.now()
    SSX_LOGGER.debug(f"Collection end time {end_time}")
    dcid.collection_complete(end_time, aborted=False)

    # NOTE no files to copy anymore but shoud write userlog here
    yield from bps.null()


@log_on_entry
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
    SSX_LOGGER.info("Closing fast shutter")
    yield from close_fast_shutter(zebra)
    yield from bps.sleep(2.0)

    # This probably should go in main then
    if parameters.detector_name == "pilatus":
        SSX_LOGGER.debug("Pilatus Acquire STOP")
        caput(pv.pilat_acquire, 0)
    elif parameters.detector_name == "eiger":
        SSX_LOGGER.debug("Eiger Acquire STOP")
        caput(pv.eiger_acquire, 0)
        caput(pv.eiger_ODcapture, "Done")
    yield from bps.sleep(0.5)

    yield from finish_i24(zebra, pmac, shutter, dcm, parameters)

    SSX_LOGGER.debug("Notify DCID of end of collection.")
    dcid.notify_end()

    SSX_LOGGER.debug("Quick summary of settings")
    SSX_LOGGER.debug(
        f"Chip name = {parameters.filename} sub_dir = {parameters.directory}"
    )


def run_fixed_target_plan(
    zebra: Zebra = inject("zebra"),
    pmac: PMAC = inject("pmac"),
    aperture: Aperture = inject("aperture"),
    backlight: DualBacklight = inject("backlight"),
    beamstop: Beamstop = inject("beamstop"),
    detector_stage: DetectorMotion = inject("detector_motion"),
    shutter: HutchShutter = inject("shutter"),
    dcm: DCM = inject("dcm"),
    mirrors: FocusMirrorsMode = inject("focus_mirrors"),
    attenuator: ReadOnlyAttenuator = inject("attenuator"),
) -> MsgGenerator:
    # Read the parameters
    parameters: FixedTargetParameters = yield from read_parameters(
        detector_stage, attenuator
    )

    # Create collection directory
    parameters.collection_directory.mkdir(parents=True, exist_ok=True)

    if parameters.chip_map:
        yield from upload_chip_map_to_geobrick(pmac, parameters.chip_map)

    beam_center_device = sup.get_beam_center_device(parameters.detector_name)

    # DCID instance - do not create yet
    dcid = DCID(emit_errors=False, expt_params=parameters)

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
            mirrors,
            beam_center_device,
            parameters,
            dcid,
        ),
        except_plan=lambda e: (yield from run_aborted_plan(pmac, dcid, e)),
        final_plan=lambda: (
            yield from tidy_up_after_collection_plan(
                zebra, pmac, shutter, dcm, parameters, dcid
            )
        ),
        auto_raise=False,
    )
