"""
Chip manager for fixed target
This version changed to python3 March2020 by RLO
"""

import json
import re
import sys
from pathlib import Path
from pprint import pformat

import bluesky.plan_stubs as bps
import numpy as np
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.attenuator.attenuator import ReadOnlyAttenuator
from dodal.devices.i24.beamstop import Beamstop, BeamstopPositions
from dodal.devices.i24.dual_backlight import BacklightPositions, DualBacklight
from dodal.devices.i24.i24_detector_motion import DetectorMotion
from dodal.devices.i24.pmac import PMAC, EncReset, LaserSettings

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import (
    ChipType,
    Fiducials,
    MappingType,
)
from mx_bluesky.beamlines.i24.serial.log import (
    SSX_LOGGER,
    _read_visit_directory_from_file,
    log_on_entry,
)
from mx_bluesky.beamlines.i24.serial.parameters import (
    FixedTargetParameters,
    get_chip_format,
    get_chip_map,
)
from mx_bluesky.beamlines.i24.serial.parameters.constants import (
    CS_FILES_PATH,
    LITEMAP_PATH,
    PARAM_FILE_PATH_FT,
    PVAR_FILE_PATH,
)
from mx_bluesky.beamlines.i24.serial.setup_beamline import Pilatus, caget, caput, pv
from mx_bluesky.beamlines.i24.serial.setup_beamline.setup_detector import (
    get_detector_type,
)

# An approximation of the chip size for the move during fiducials alignment.
CHIP_MOVES = {
    ChipType.Oxford: 25.40,
    ChipType.OxfordInner: 24.60,
    ChipType.Custom: 25.40,
    ChipType.Minichip: 25.40,
}
OXFORD_CHIP_WIDTH = 8
PVAR_TEMPLATE = f"P3%0{2}d1"
CHIPTYPE_PV = pv.me14e_gp1
MAPTYPE_PV = pv.me14e_gp2
NUM_EXPOSURES_PV = pv.me14e_gp3
PUMP_REPEAT_PV = pv.me14e_gp4
MAP_FILEPATH_PV = pv.me14e_gp5


@log_on_entry
def initialise_stages(
    pmac: PMAC = inject("pmac"),
) -> MsgGenerator:
    """Initialise the portable stages PVs, usually used only once right after setting \
        up the stages either after use at different facility.
    """
    group = "initialise_stages"
    SSX_LOGGER.info("Setting velocity, acceleration and limits for stages")

    yield from bps.abs_set(pmac.x.velocity, 20, group=group)
    yield from bps.abs_set(pmac.y.velocity, 20, group=group)
    yield from bps.abs_set(pmac.z.velocity, 20, group=group)
    yield from bps.abs_set(pmac.x.acceleration_time, 0.01, group=group)
    yield from bps.abs_set(pmac.y.acceleration_time, 0.01, group=group)
    yield from bps.abs_set(pmac.z.acceleration_time, 0.01, group=group)
    yield from bps.abs_set(pmac.x.high_limit_travel, 30, group=group)
    yield from bps.abs_set(pmac.x.low_limit_travel, -29, group=group)
    yield from bps.abs_set(pmac.y.high_limit_travel, 30, group=group)
    yield from bps.abs_set(pmac.y.low_limit_travel, -30, group=group)
    yield from bps.abs_set(pmac.z.high_limit_travel, 5.1, group=group)
    yield from bps.abs_set(pmac.z.low_limit_travel, -4.1, group=group)
    caput(CHIPTYPE_PV, 1)  # chip type
    caput(MAPTYPE_PV, 0)  # map type
    caput(NUM_EXPOSURES_PV, 1)  # num exposures
    caput(PUMP_REPEAT_PV, 0)  # pump repeat
    caput(pv.me14e_filepath, "test")
    caput(pv.me14e_chip_name, "albion")
    caput(pv.me14e_dcdetdist, 1480)
    caput(pv.me14e_exptime, 0.01)
    yield from bps.abs_set(pmac.enc_reset, EncReset.ENC5, group=group)
    yield from bps.abs_set(pmac.enc_reset, EncReset.ENC6, group=group)
    yield from bps.abs_set(pmac.enc_reset, EncReset.ENC7, group=group)
    yield from bps.abs_set(pmac.enc_reset, EncReset.ENC8, group=group)

    caput(pv.pilat_cbftemplate, 0)

    yield from bps.sleep(0.1)
    SSX_LOGGER.info("Clearing General Purpose PVs 1-120")
    for i in range(4, 120):
        if i == 100:
            # Do not clear visit PV
            continue
        pvar = "ME14E-MO-IOC-01:GP" + str(i)
        caput(pvar, 0)
        sys.stdout.write(".")
        sys.stdout.flush()

    SSX_LOGGER.info("Initialisation of the stages complete")
    yield from bps.wait(group=group)


@log_on_entry
def read_parameters(
    detector_stage: DetectorMotion,
    attenuator: ReadOnlyAttenuator,
) -> MsgGenerator:
    """ Read the parameters from user input and create the parameter model for a fixed \
        target collection.

    Args:
        detector_stage (DetectorMotion): The detector stage device.
        attenuator (ReadOnlyAttenuator): A read-only attenuator device to get the \
            transmission value.

    Returns:
        FixedTargetParameters: Parameter model for fixed target collections

    """
    SSX_LOGGER.info("Creating parameter model from input.")

    filename = caget(pv.me14e_chip_name)
    det_type = yield from get_detector_type(detector_stage)
    chip_params = get_chip_format(ChipType(int(caget(CHIPTYPE_PV))))
    map_type = int(caget(MAPTYPE_PV))
    if map_type == MappingType.Lite and chip_params.chip_type in [
        ChipType.Oxford,
        ChipType.OxfordInner,
    ]:
        chip_map = get_chip_map()
    else:
        chip_map = []
    pump_repeat = int(caget(PUMP_REPEAT_PV))

    # If file name ends in a digit this causes processing/pilatus pain.
    # Append an underscore
    if isinstance(det_type, Pilatus):
        caput(pv.pilat_cbftemplate, 0)
        m = re.search(r"\d+$", filename)
        if m is not None:
            # Note for future reference. Appending underscore causes more hassle and
            # high probability of users accidentally overwriting data. Use a dash
            filename = filename + "-"
            SSX_LOGGER.debug(
                f"Requested filename ends in a number. Appended dash: {filename}"
            )

    transmission = yield from bps.rd(attenuator.actual_transmission)

    params_dict = {
        "visit": _read_visit_directory_from_file().as_posix(),  # noqa
        "directory": caget(pv.me14e_filepath),
        "filename": filename,
        "exposure_time_s": caget(pv.me14e_exptime),
        "detector_distance_mm": caget(pv.me14e_dcdetdist),
        "detector_name": str(det_type),
        "num_exposures": int(caget(NUM_EXPOSURES_PV)),
        "transmission": transmission,
        "chip": chip_params.model_dump(),
        "map_type": map_type,
        "pump_repeat": pump_repeat,
        "checker_pattern": bool(caget(pv.me14e_gp111)),
        "chip_map": chip_map,
        "laser_dwell_s": float(caget(pv.me14e_gp103)) if pump_repeat != 0 else 0.0,
        "laser_delay_s": float(caget(pv.me14e_gp110)) if pump_repeat != 0 else 0.0,
        "pre_pump_exposure_s": float(caget(pv.me14e_gp109))
        if pump_repeat != 0
        else None,
    }

    SSX_LOGGER.info("Parameters for I24 serial collection: \n")
    SSX_LOGGER.info(pformat(params_dict))

    yield from bps.null()
    return FixedTargetParameters(**params_dict)


def scrape_pvar_file(fid: str, pvar_dir: Path = PVAR_FILE_PATH):
    block_start_list = []

    with open(pvar_dir / fid) as f:
        lines = f.readlines()
    for line in lines:
        line = line.rstrip()
        if line.startswith("#"):
            continue
        elif line.startswith("P3000"):
            continue
        elif line.startswith("P3011"):
            continue
        elif not len(line.split(" ")) == 2:
            continue
        else:
            entry = line.split(" ")
            block_num = entry[0][2:4]
            x = entry[0].split("=")[1]
            y = entry[1].split("=")[1]
            block_start_list.append([block_num, x, y])
    return block_start_list


@log_on_entry
def define_current_chip(
    chipid: str = "oxford",
    pmac: PMAC = inject("pmac"),
) -> MsgGenerator:
    SSX_LOGGER.debug("Run load stock map for just the first block")
    yield from load_stock_map("Just The First Block")
    """
    Not sure what this is for:
    print 'Setting Mapping Type to Lite'
    caput(pv.me14e_gp2, 1)
    """
    chip_type = int(caget(CHIPTYPE_PV))
    SSX_LOGGER.info(f"Chip type:{chip_type} Chipid:{chipid}")
    if chipid == "oxford":
        caput(CHIPTYPE_PV, 0)

    with open(PVAR_FILE_PATH / f"{chipid}.pvar") as f:
        SSX_LOGGER.info(f"Opening {chipid}.pvar")
        for line in f.readlines():
            if line.startswith("#"):
                continue
            line_from_file = line.rstrip("\n")
            SSX_LOGGER.info(f"{line_from_file}")
            yield from bps.abs_set(pmac.pmac_string, line_from_file)


@log_on_entry
def upload_chip_map_to_geobrick(pmac: PMAC, chip_map: list[int]) -> MsgGenerator:
    """Upload the map parameters for an Oxford-type chip (width=8) to the geobrick.

    Args:
        pmac (PMAC): The PMAC device.
        chip_map (list[int]): A list of selected blocks to be collected.

    """
    SSX_LOGGER.info("Uploading Parameters for Oxford Chip to the GeoBrick")
    SSX_LOGGER.info(f"Chipid {ChipType.Oxford}, width {OXFORD_CHIP_WIDTH}")
    for block in range(1, 65):
        value = 1 if block in chip_map else 0
        pvar = PVAR_TEMPLATE % block
        pvar_str = f"{pvar}={value}"
        SSX_LOGGER.debug(f"Set {pvar_str} for block {block}")
        yield from bps.abs_set(pmac.pmac_string, pvar_str, wait=True)
        # Wait for PMAC to be done processing PVAR string
        yield from bps.sleep(0.02)
    SSX_LOGGER.debug("Upload parameters done.")


@log_on_entry
def load_stock_map(map_choice: str = "clear") -> MsgGenerator:
    # TODO See https://github.com/DiamondLightSource/mx_bluesky/issues/122
    SSX_LOGGER.info("Adjusting Lite Map EDM Screen")
    SSX_LOGGER.debug("Please wait, adjusting lite map")
    #
    r33 = [19, 18, 17, 26, 31, 32, 33, 24, 25]
    r55 = [9, 10, 11, 12, 13, 16, 27, 30, 41, 40, 39, 38, 37, 34, 23, 20] + r33
    r77 = [
        7,
        6,
        5,
        4,
        3,
        2,
        1,
        14,
        15,
        28,
        29,
        42,
        43,
        44,
        45,
        46,
        47,
        48,
        49,
        36,
        35,
        22,
        21,
        8,
    ] + r55
    #
    h33 = [3, 2, 1, 6, 7, 8, 9, 4, 5]
    x33 = [31, 32, 33, 40, 51, 50, 49, 42, 41]
    x55 = [25, 24, 23, 22, 21, 34, 39, 52, 57, 58, 59, 60, 61, 48, 43, 30] + x33
    x77 = [
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        20,
        35,
        38,
        53,
        56,
        71,
        70,
        69,
        68,
        67,
        66,
        65,
        62,
        47,
        44,
        29,
        26,
    ] + x55
    x99 = [
        9,
        8,
        7,
        6,
        5,
        4,
        3,
        2,
        1,
        18,
        19,
        36,
        37,
        54,
        55,
        72,
        73,
        74,
        75,
        76,
        77,
        78,
        79,
        80,
        81,
        64,
        63,
        46,
        45,
        28,
        27,
        10,
    ] + x77  # noqa
    x44 = [22, 21, 20, 19, 30, 35, 46, 45, 44, 43, 38, 27, 28, 29, 36, 37]
    x49 = [x + 1 for x in range(49)]
    x66 = [
        10,
        11,
        12,
        13,
        14,
        15,
        18,
        31,
        34,
        47,
        50,
        51,
        52,
        53,
        54,
        55,
        42,
        39,
        26,
        23,
    ] + x44
    x88 = [
        8,
        7,
        6,
        5,
        4,
        3,
        2,
        1,
        16,
        17,
        32,
        33,
        48,
        49,
        64,
        63,
        62,
        61,
        60,
        59,
        58,
        57,
        56,
        41,
        40,
        25,
        24,
        9,
    ] + x66
    #
    # Columns for doing half chips
    c1 = [1, 2, 3, 4, 5, 6, 7, 8]
    c2 = [9, 10, 11, 12, 13, 14, 15, 16]
    c3 = [17, 18, 19, 20, 21, 22, 23, 24]
    c4 = [25, 26, 27, 28, 29, 30, 31, 32]
    c5 = [33, 34, 35, 36, 37, 38, 39, 40]
    c6 = [41, 42, 43, 44, 45, 46, 47, 48]
    c7 = [49, 50, 51, 52, 53, 54, 55, 56]
    c8 = [57, 58, 59, 60, 61, 62, 63, 64]
    half1 = c1 + c2 + c3 + c4
    half2 = c5 + c6 + c7 + c8

    map_dict = {}
    map_dict["Just The First Block"] = [1]
    map_dict["clear"] = []
    #
    map_dict["r33"] = r33
    map_dict["r55"] = r55
    map_dict["r77"] = r77
    #
    map_dict["h33"] = h33
    #
    map_dict["x33"] = x33
    map_dict["x44"] = x44
    map_dict["x49"] = x49
    map_dict["x55"] = x55
    map_dict["x66"] = x66
    map_dict["x77"] = x77
    map_dict["x88"] = x88
    map_dict["x99"] = x99

    map_dict["half1"] = half1
    map_dict["half2"] = half2

    SSX_LOGGER.info("Clearing GP 10-74")  # Actually 11-44
    for i in range(1, 65):
        pvar = "ME14E-MO-IOC-01:GP" + str(i + 10)
        caput(pvar, 0)
        sys.stdout.write(".")
        sys.stdout.flush()
    SSX_LOGGER.info("Map cleared")
    SSX_LOGGER.info(f"Loading Map Choice {map_choice}")
    for i in map_dict[map_choice]:
        pvar = "ME14E-MO-IOC-01:GP" + str(i + 10)
        caput(pvar, 1)
    SSX_LOGGER.debug("Load stock map done.")
    yield from bps.null()


@log_on_entry
def load_lite_map() -> MsgGenerator:
    SSX_LOGGER.debug("Run load stock map with 'clear' setting.")
    yield from load_stock_map("clear")
    # fmt: off
    # Oxford_block_dict is wrong (columns and rows need to flip) added in script below to generate it automatically however kept this for backwards compatiability/reference
    oxford_block_dict = {   # noqa: F841
        'A1': '01', 'A2': '02', 'A3': '03', 'A4': '04', 'A5': '05', 'A6': '06', 'A7': '07', 'A8': '08',
        'B1': '16', 'B2': '15', 'B3': '14', 'B4': '13', 'B5': '12', 'B6': '11', 'B7': '10', 'B8': '09',
        'C1': '17', 'C2': '18', 'C3': '19', 'C4': '20', 'C5': '21', 'C6': '22', 'C7': '23', 'C8': '24',
        'D1': '32', 'D2': '31', 'D3': '30', 'D4': '29', 'D5': '28', 'D6': '27', 'D7': '26', 'D8': '25',
        'E1': '33', 'E2': '34', 'E3': '35', 'E4': '36', 'E5': '37', 'E6': '38', 'E7': '39', 'E8': '40',
        'F1': '48', 'F2': '47', 'F3': '46', 'F4': '45', 'F5': '44', 'F6': '43', 'F7': '42', 'F8': '41',
        'G1': '49', 'G2': '50', 'G3': '51', 'G4': '52', 'G5': '53', 'G6': '54', 'G7': '55', 'G8': '56',
        'H1': '64', 'H2': '63', 'H3': '62', 'H4': '61', 'H5': '60', 'H6': '59', 'H7': '58', 'H8': '57',
    }
    # fmt: on
    chip_type = int(caget(CHIPTYPE_PV))
    if chip_type in [ChipType.Oxford, ChipType.OxfordInner]:
        SSX_LOGGER.info("Oxford Block Order")
        rows = ["A", "B", "C", "D", "E", "F", "G", "H"]
        columns = list(range(1, 10))
        btn_names = {}
        flip = True
        for x, column in enumerate(columns):
            for y, row in enumerate(rows):
                i = x * 8 + y
                if i % 8 == 0 and flip is False:
                    flip = True
                    z = 8 - (y + 1)
                elif i % 8 == 0 and flip is True:
                    flip = False
                    z = y
                elif flip is False:
                    z = y
                elif flip is True:
                    z = 8 - (y + 1)
                else:
                    SSX_LOGGER.warning("Problem in Chip Grid Creation")
                    break
                button_name = str(row) + str(column)
                lab_num = x * 8 + z
                label = f"{lab_num + 1:02d}"
                btn_names[button_name] = label
        block_dict = btn_names
    else:
        raise ValueError(f"{chip_type=} unrecognised")

    litemap_fid = f"{caget(MAP_FILEPATH_PV)}.lite"
    SSX_LOGGER.info("Please wait, loading LITE map")
    SSX_LOGGER.debug("Loading Lite Map")
    SSX_LOGGER.info("Opening %s" % (LITEMAP_PATH / litemap_fid))
    with open(LITEMAP_PATH / litemap_fid) as fh:
        f = fh.readlines()
    for line in f:
        entry = line.split()
        block_name = entry[0]
        yesno = entry[1]
        block_num = block_dict[block_name]
        pvar = "ME14E-MO-IOC-01:GP" + str(int(block_num) + 10)
        SSX_LOGGER.info(f"Block: {block_name} \tScanned: {yesno} \tPVAR: {pvar}")
    SSX_LOGGER.debug("Load lite map done")
    yield from bps.null()


@log_on_entry
def moveto(place: str = "origin", pmac: PMAC = inject("pmac")) -> MsgGenerator:
    SSX_LOGGER.info(f"Move to: {place}")
    if place == Fiducials.zero:
        SSX_LOGGER.info("Chip aspecific move.")
        yield from bps.trigger(pmac.to_xyz_zero)
        return

    chip_type = ChipType(int(caget(CHIPTYPE_PV)))
    SSX_LOGGER.info(f"Chip type is {chip_type}")
    if chip_type not in list(ChipType):
        SSX_LOGGER.warning("Unknown chip_type move")
        return

    SSX_LOGGER.info(f"{str(chip_type)} Move")
    chip_move = CHIP_MOVES[chip_type]

    if place == Fiducials.origin:
        yield from bps.mv(pmac.x, 0.0, pmac.y, 0.0)
    if place == Fiducials.fid1:
        yield from bps.mv(pmac.x, chip_move, pmac.y, 0.0)
    if place == Fiducials.fid2:
        yield from bps.mv(pmac.x, 0.0, pmac.y, chip_move)


@log_on_entry
def moveto_preset(
    place: str,
    pmac: PMAC = inject("pmac"),
    beamstop: Beamstop = inject("beamstop"),
    backlight: DualBacklight = inject("backlight"),
    det_stage: DetectorMotion = inject("detector_motion"),
) -> MsgGenerator:
    # Non Chip Specific Move
    if place == "zero":
        SSX_LOGGER.info(f"Moving to {place}")
        yield from bps.trigger(pmac.to_xyz_zero)

    elif place == "load_position":
        SSX_LOGGER.info("load position")
        yield from bps.abs_set(
            beamstop.pos_select, BeamstopPositions.ROBOT, group=place
        )
        yield from bps.abs_set(backlight, BacklightPositions.OUT, group=place)
        yield from bps.abs_set(det_stage.z, 1300, group=place)
        yield from bps.wait(group=place)

    elif place == "collect_position":
        SSX_LOGGER.info("collect position")
        caput(pv.me14e_filter, 20)
        yield from bps.mv(pmac.x, 0.0, pmac.y, 0.0, pmac.z, 0.0)
        yield from bps.abs_set(
            beamstop.pos_select, BeamstopPositions.DATA_COLLECTION, group=place
        )
        yield from bps.abs_set(backlight, BacklightPositions.IN, group=place)
        yield from bps.wait(group=place)

    elif place == "microdrop_position":
        SSX_LOGGER.info("microdrop align position")
        yield from bps.mv(pmac.x, 6.0, pmac.y, -7.8, pmac.z, 0.0)


@log_on_entry
def laser_control(laser_setting: str, pmac: PMAC = inject("pmac")) -> MsgGenerator:
    SSX_LOGGER.info(f"Move to: {laser_setting}")
    if laser_setting == "laser1on":  # these are in laser edm
        SSX_LOGGER.info("Laser 1 /BNC2 shutter is open")
        # Use M712 = 0 if triggering on falling edge. M712 =1 if on rising edge
        # Be sure to also change laser1off
        # caput(pv.me14e_pmac_str, ' M712=0 M711=1')
        yield from bps.abs_set(pmac.laser, LaserSettings.LASER_1_ON, wait=True)

    elif laser_setting == "laser1off":
        SSX_LOGGER.info("Laser 1 shutter is closed")
        yield from bps.abs_set(pmac.laser, LaserSettings.LASER_1_OFF, wait=True)

    elif laser_setting == "laser2on":
        SSX_LOGGER.info("Laser 2 / BNC3 shutter is open")
        yield from bps.abs_set(pmac.laser, LaserSettings.LASER_2_ON, wait=True)

    elif laser_setting == "laser2off":
        SSX_LOGGER.info("Laser 2 shutter is closed")
        yield from bps.abs_set(pmac.laser, LaserSettings.LASER_2_OFF, wait=True)

    elif laser_setting == "laser1burn":
        led_burn_time = caget(pv.me14e_gp103)
        SSX_LOGGER.info("Laser 1  on")
        SSX_LOGGER.info(f"Burn time is {led_burn_time} s")
        yield from bps.abs_set(pmac.laser, LaserSettings.LASER_1_ON, wait=True)
        yield from bps.sleep(float(led_burn_time))
        SSX_LOGGER.info("Laser 1 off")
        yield from bps.abs_set(pmac.laser, LaserSettings.LASER_1_OFF, wait=True)

    elif laser_setting == "laser2burn":
        led_burn_time = caget(pv.me14e_gp109)
        SSX_LOGGER.info("Laser 2 on")
        SSX_LOGGER.info(f"burntime {led_burn_time} s")
        yield from bps.abs_set(pmac.laser, LaserSettings.LASER_2_ON, wait=True)
        yield from bps.sleep(float(led_burn_time))
        SSX_LOGGER.info("Laser 2 off")
        yield from bps.abs_set(pmac.laser, LaserSettings.LASER_2_OFF, wait=True)


@log_on_entry
def scrape_mtr_directions(motor_file_path: Path = CS_FILES_PATH):
    with open(motor_file_path / "motor_direction.txt") as f:
        lines = f.readlines()
    mtr1_dir, mtr2_dir, mtr3_dir = 1.0, 1.0, 1.0
    for line in lines:
        if line.startswith("mtr1"):
            mtr1_dir = float(line.split("=")[1])
        elif line.startswith("mtr2"):
            mtr2_dir = float(line.split("=")[1])
        elif line.startswith("mtr3"):
            mtr3_dir = float(line.split("=")[1])
        else:
            continue
    SSX_LOGGER.debug(f"mt1_dir {mtr1_dir} mtr2_dir {mtr2_dir} mtr3_dir {mtr3_dir}")
    return mtr1_dir, mtr2_dir, mtr3_dir


@log_on_entry
def fiducial(point: int = 1, pmac: PMAC = inject("pmac")) -> MsgGenerator:
    scale = 10000.0  # noqa: F841

    mtr1_dir, mtr2_dir, mtr3_dir = scrape_mtr_directions(CS_FILES_PATH)

    rbv_1 = yield from bps.rd(pmac.x.user_readback)
    rbv_2 = yield from bps.rd(pmac.y.user_readback)
    rbv_3 = yield from bps.rd(pmac.z.user_readback)

    output_param_path = PARAM_FILE_PATH_FT
    output_param_path.mkdir(parents=True, exist_ok=True)
    SSX_LOGGER.info(f"Writing Fiducial File {output_param_path}/fiducial_{point}.txt")
    SSX_LOGGER.info("MTR\tRBV\tRAW\tCorr\tf_value")
    SSX_LOGGER.info(f"MTR1\t{rbv_1:1.4f}\t{mtr1_dir:f}")
    SSX_LOGGER.info(f"MTR2\t{rbv_2:1.4f}\t{mtr2_dir:f}")
    SSX_LOGGER.info(f"MTR3\t{rbv_3:1.4f}\t{mtr3_dir:f}")

    with open(output_param_path / f"fiducial_{point}.txt", "w") as f:
        f.write("MTR\tRBV\tCorr\n")
        f.write(f"MTR1\t{rbv_1:1.4f}\t{mtr1_dir:f}\n")
        f.write(f"MTR2\t{rbv_2:1.4f}\t{mtr2_dir:f}\n")
        f.write(f"MTR3\t{rbv_3:1.4f}\t{mtr3_dir:f}")
    SSX_LOGGER.info(f"Fiducial {point} set.")
    yield from bps.null()


def scrape_mtr_fiducials(
    point: int, param_path: Path = PARAM_FILE_PATH_FT
) -> tuple[float, float, float]:
    with open(param_path / f"fiducial_{point}.txt") as f:
        f_lines = f.readlines()[1:]
    f_x = float(f_lines[0].rsplit()[1])
    f_y = float(f_lines[1].rsplit()[1])
    f_z = float(f_lines[2].rsplit()[1])
    return f_x, f_y, f_z


@log_on_entry
def cs_maker(pmac: PMAC = inject("pmac")) -> MsgGenerator:
    """
    Coordinate system.

    Values for scalex, scaley, scalez, and skew, as well as the sign of
    Sx, Sy, Sz are stored in a .json file and should be modified there.
    Location of file: src/mx_bluesky/i24/serial/parameters/cs_maker.json

    Theory
    Rx: rotation about X-axis, pitch
    Ry: rotation about Y-axis, yaw
    Rz: rotation about Z-axis, roll
    The order of rotation is Roll->Yaw->Pitch (Rx*Ry*Rz)
    Rx           Ry          Rz
    |1  0   0| | Cy  0 Sy| |Cz -Sz 0|   | CyCz        -CxSz         Sy  |
    |0 Cx -Sx|*|  0  1  0|*|Sz  Cz 0| = | SxSyCz+CxSz -SxSySz+CxCz -SxCy|
    |0 Sx  Cx| |-Sy  0 Cy| | 0   0 1|   |-CxSyCz+SxSz  CxSySz+SxCz  CxCy|

    BELOW iS TEST TEST (CLOCKWISE)
    Rx           Ry          Rz
    |1  0   0| | Cy 0 -Sy| |Cz  Sz 0|   | CyCz         CxSz         -Sy |
    |0 Cx  Sx|*|  0  1  0|*|-Sz Cz 0| = | SxSyCz-CxSz  SxSySz+CxCz  SxCy|
    |0 -Sx Cx| | Sy  0 Cy| | 0   0 1|   | CxSyCz+SxSz  CxSySz-SxCz  CxCy|


    Skew:
    Skew is the difference between the Sz1 and Sz2 after rotation is taken out.
    This should be measured in situ prior to expriment, ie. measure by hand using
    opposite and adjacent RBV after calibration of scale factors.
    """
    chip_type = int(caget(CHIPTYPE_PV))
    fiducial_dict = {}
    fiducial_dict[0] = [25.400, 25.400]
    fiducial_dict[1] = [24.600, 24.600]
    fiducial_dict[2] = [25.400, 25.400]
    fiducial_dict[3] = [18.25, 18.25]
    SSX_LOGGER.info(f"Chip type is {chip_type} with size {fiducial_dict[chip_type]}")

    mtr1_dir, mtr2_dir, mtr3_dir = scrape_mtr_directions()
    f1_x, f1_y, f1_z = scrape_mtr_fiducials(1)
    f2_x, f2_y, f2_z = scrape_mtr_fiducials(2)
    SSX_LOGGER.info(f"mtr1 direction: {mtr1_dir}")
    SSX_LOGGER.info(f"mtr2 direction: {mtr2_dir}")
    SSX_LOGGER.info(f"mtr3 direction: {mtr3_dir}")

    # Scale parameters saved in json file
    try:
        with open(CS_FILES_PATH / "cs_maker.json") as fh:
            cs_info = json.load(fh)
    except json.JSONDecodeError:
        SSX_LOGGER.error("Invalid JSON file.")
        raise

    try:
        scalex, scaley, scalez = (
            float(cs_info["scalex"]),
            float(cs_info["scaley"]),
            float(cs_info["scalez"]),
        )
        skew = float(cs_info["skew"])
        Sx_dir, Sy_dir, Sz_dir = (
            int(cs_info["Sx_dir"]),
            int(cs_info["Sy_dir"]),
            int(cs_info["Sz_dir"]),
        )
    except KeyError:
        SSX_LOGGER.error("Wrong or missing key in the cs json file.")
        raise

    def check_dir(val):
        if val not in [1, -1]:
            raise ValueError("Wrong value for direction. Please set to either -1 or 1.")

    check_dir(Sx_dir)
    check_dir(Sy_dir)
    check_dir(Sz_dir)

    # Rotation Around Z
    # If stages upsidedown (I24) change sign of Sz
    Sz1 = -1 * f1_y / fiducial_dict[chip_type][0]
    Sz2 = f2_x / fiducial_dict[chip_type][1]
    Sz = Sz_dir * ((Sz1 + Sz2) / 2)
    Cz = np.sqrt(1 - Sz**2)
    SSX_LOGGER.info(f"Sz1 , {Sz1:1.4f}, {np.degrees(np.arcsin(Sz1)):1.4f}")
    SSX_LOGGER.info(f"Sz2 , {Sz2:1.4f}, {np.degrees(np.arcsin(Sz2)):1.4f}")
    SSX_LOGGER.info(f"Sz , {Sz:1.4f}, {np.degrees(np.arcsin(Sz)):1.4f}")
    SSX_LOGGER.info(f"Cz , {Cz:1.4f}, {np.degrees(np.arcsin(Cz)):1.4f}")
    # Rotation Around Y
    Sy = Sy_dir * f1_z / fiducial_dict[chip_type][0]
    Cy = np.sqrt(1 - Sy**2)
    SSX_LOGGER.info(f"Sy , {Sy:1.4f}, {np.degrees(np.arcsin(Sy)):1.4f}")
    SSX_LOGGER.info(f"Cy , {Cy:1.4f}, {np.degrees(np.arcsin(Cy)):1.4f}")
    # Rotation Around X
    # If stages upsidedown (I24) change sign of Sx
    Sx = Sx_dir * f2_z / fiducial_dict[chip_type][1]
    Cx = np.sqrt(1 - Sx**2)
    SSX_LOGGER.info(f"Sx , {Sx:1.4f}, {np.degrees(np.arcsin(Sx)):1.4f}")
    SSX_LOGGER.info(f"Cx , {Cx:1.4f}, {np.degrees(np.arcsin(Cx)):1.4f}")

    x1factor = mtr1_dir * scalex * (Cy * Cz)
    y1factor = mtr2_dir * scaley * (-1.0 * Cx * Sz)
    z1factor = mtr3_dir * scalez * Sy

    x2factor = mtr1_dir * scalex * ((Sx * Sy * Cz) + (Cx * Sz))
    y2factor = mtr2_dir * scaley * ((Cx * Cz) - (Sx * Sy * Sz))
    z2factor = mtr3_dir * scalez * (-1.0 * Sx * Cy)

    x3factor = mtr1_dir * scalex * ((Sx * Sz) - (Cx * Sy * Cz))
    y3factor = mtr2_dir * scaley * ((Cx * Sy * Sz) + (Sx * Cz))
    z3factor = mtr3_dir * scalez * (Cx * Cy)

    SSX_LOGGER.info(f"Skew being used is: {skew:1.4f}")
    s1 = np.degrees(np.arcsin(Sz1))
    s2 = np.degrees(np.arcsin(Sz2))
    rot = np.degrees(np.arcsin((Sz1 + Sz2) / 2))
    calc_skew = (s1 - rot) - (s2 - rot)
    SSX_LOGGER.info(f"s1:{s1:1.4f} s2:{s2:1.4f} rot:{rot:1.4f}")
    SSX_LOGGER.info(f"Calculated rotation from current fiducials is: {rot:1.4f}")
    SSX_LOGGER.info(f"Calculated Skew from current fiducials is: {calc_skew:1.4f}")
    SSX_LOGGER.info("Calculated Skew has been known to have the wrong sign")

    sinD = np.sin((skew / 2) * (np.pi / 180))
    cosD = np.cos((skew / 2) * (np.pi / 180))
    new_x1factor = (x1factor * cosD) + (y1factor * sinD)
    new_y1factor = (x1factor * sinD) + (y1factor * cosD)
    new_x2factor = (x2factor * cosD) + (y2factor * sinD)
    new_y2factor = (x2factor * sinD) + (y2factor * cosD)

    cs1 = f"#1->{new_x1factor:+1.3f}X{new_y1factor:+1.3f}Y{z1factor:+1.3f}Z"
    cs2 = f"#2->{new_x2factor:+1.3f}X{new_y2factor:+1.3f}Y{z2factor:+1.3f}Z"
    cs3 = f"#3->{x3factor:+1.3f}X{y3factor:+1.3f}Y{z3factor:+1.3f}Z"
    SSX_LOGGER.info(f"PMAC strings. \ncs1: {cs1} \ncs2: {cs2}cs3: {cs3}")
    SSX_LOGGER.info(
        """These next values should be 1.
        This is the sum of the squares of the factors divided by their scale."""
    )
    sqfact1 = np.sqrt(x1factor**2 + y1factor**2 + z1factor**2) / scalex
    sqfact2 = np.sqrt(x2factor**2 + y2factor**2 + z2factor**2) / scaley
    sqfact3 = np.sqrt(x3factor**2 + y3factor**2 + z3factor**2) / scalez
    SSX_LOGGER.info(f"{sqfact1:1.4f} \n {sqfact2:1.4f} \n {sqfact3:1.4f}")
    SSX_LOGGER.debug("Long wait, please be patient")
    yield from bps.trigger(pmac.to_xyz_zero)
    yield from bps.sleep(2.5)
    yield from set_pmac_strings_for_cs(pmac, {"cs1": cs1, "cs2": cs2, "cs3": cs3})
    yield from bps.trigger(pmac.to_xyz_zero)
    yield from bps.sleep(2.5)
    yield from bps.trigger(pmac.home, wait=True)
    yield from bps.sleep(2.5)
    SSX_LOGGER.debug(f"Chip_type is {chip_type}")
    if chip_type == 0:
        yield from bps.abs_set(pmac.pmac_string, "!x0.4y0.4", wait=True)
        yield from bps.sleep(2.5)
        yield from bps.trigger(pmac.home, wait=True)
    else:
        yield from bps.trigger(pmac.home, wait=True)
    SSX_LOGGER.debug("CSmaker done.")
    yield from bps.null()


def cs_reset(pmac: PMAC = inject("pmac")) -> MsgGenerator:
    """Used to clear CS when using Custom Chip"""
    cs1 = "#1->10000X+0Y+0Z"
    cs2 = "#2->+0X-10000Y+0Z"
    cs3 = "#3->0X+0Y-10000Z"
    strg = "\n".join([cs1, cs2, cs3])
    print(strg)
    yield from set_pmac_strings_for_cs(pmac, {"cs1": cs1, "cs2": cs2, "cs3": cs3})
    SSX_LOGGER.debug("CSreset Done")
    yield from bps.null()


def set_pmac_strings_for_cs(pmac: PMAC, cs_str: dict):
    """ A plan to set the pmac_string for the (x,y,z) axes while making or resetting \
        the coordinate system.

    Args:
        pmac (PMAC): PMAC device
        cs_str (dict): A dictionary containing a string for each axis, in the format: \
            {
                "cs1": "#1->1X+0Y+0Z",
                "cs2": "#2->...",
                "cs3": "#3->...",
            }

    Note. On the PMAC the axes allocations are: #1 - X, #2 - Y, #3 - Z.
    """
    yield from bps.abs_set(pmac.pmac_string, "&2", wait=True)
    yield from bps.abs_set(pmac.pmac_string, cs_str["cs1"], wait=True)
    yield from bps.abs_set(pmac.pmac_string, cs_str["cs2"], wait=True)
    yield from bps.abs_set(pmac.pmac_string, cs_str["cs3"], wait=True)


@log_on_entry
def pumpprobe_calc() -> MsgGenerator:
    # TODO See https://github.com/DiamondLightSource/mx_bluesky/issues/122
    SSX_LOGGER.info("Calculate and show exposure and dwell time for each option.")
    exptime = float(caget(pv.me14e_exptime))
    pumpexptime = float(caget(pv.me14e_gp103))
    movetime = 0.008
    SSX_LOGGER.info(f"X-ray exposure time {exptime}")
    SSX_LOGGER.info(f"Laser dwell time {pumpexptime}")
    repeat1 = 2 * 20 * (movetime + (pumpexptime + exptime) / 2)
    repeat2 = 4 * 20 * (movetime + (pumpexptime + exptime) / 2)
    repeat3 = 6 * 20 * (movetime + (pumpexptime + exptime) / 2)
    repeat5 = 10 * 20 * (movetime + (pumpexptime + exptime) / 2)
    repeat10 = 20 * 20 * (movetime + (pumpexptime + exptime) / 2)
    for pv_name, repeat in (
        (pv.me14e_gp104, repeat1),
        (pv.me14e_gp105, repeat2),
        (pv.me14e_gp106, repeat3),
        (pv.me14e_gp107, repeat5),
        (pv.me14e_gp108, repeat10),
    ):
        rounded = round(repeat, 4)
        caput(pv_name, rounded)
        SSX_LOGGER.info(f"Repeat ({pv_name}): {rounded} s")
    SSX_LOGGER.debug("PP calculations done")
    yield from bps.null()


@log_on_entry
def block_check(pmac: PMAC = inject("pmac")) -> MsgGenerator:
    # TODO See https://github.com/DiamondLightSource/mx_bluesky/issues/117
    caput(pv.me14e_gp9, 0)
    while True:
        if int(caget(pv.me14e_gp9)) == 0:
            chip_type = int(caget(CHIPTYPE_PV))
            if chip_type == ChipType.Minichip:
                SSX_LOGGER.info("Oxford mini chip in use.")
                block_start_list = scrape_pvar_file("minichip_oxford.pvar")
            elif chip_type == ChipType.Custom:
                SSX_LOGGER.error("This is a custom chip, no block check available!")
                raise ValueError(
                    "Chip type set to 'custom', which has no block check."
                    "If not using a custom chip, please double check chip in the GUI."
                )
            else:
                SSX_LOGGER.warning("Default is Oxford chip block start list.")
                block_start_list = scrape_pvar_file("oxford.pvar")
            for entry in block_start_list:
                if int(caget(pv.me14e_gp9)) != 0:
                    SSX_LOGGER.warning("Block Check Aborted")
                    yield from bps.sleep(1.0)
                    break
                block, x, y = entry
                SSX_LOGGER.debug(f"Block: {block} -> (x={x} y={y})")
                yield from bps.abs_set(pmac.pmac_string, f"!x{x}y{y}", wait=True)
                yield from bps.sleep(0.4)
        else:
            SSX_LOGGER.warning("Block Check Aborted due to GP 9 not equalling 0")
            break
        break
    SSX_LOGGER.debug("Block check done")
    yield from bps.null()
