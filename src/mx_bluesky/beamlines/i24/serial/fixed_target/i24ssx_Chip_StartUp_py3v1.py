"""
Startup utilities for chip
"""

import os
import string
import time
from pathlib import Path

import numpy as np

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import ChipType
from mx_bluesky.beamlines.i24.serial.log import SSX_LOGGER, log_on_entry
from mx_bluesky.beamlines.i24.serial.parameters import (
    FixedTargetParameters,
    get_chip_format,
)
from mx_bluesky.beamlines.i24.serial.parameters.constants import (
    HEADER_FILES_PATH,
    PARAM_FILE_NAME,
    PARAM_FILE_PATH_FT,
)


def read_parameter_file(
    param_path: Path | str = PARAM_FILE_PATH_FT,
) -> FixedTargetParameters:
    if not isinstance(param_path, Path):
        param_path = Path(param_path)
    params_file = param_path / PARAM_FILE_NAME
    params = FixedTargetParameters.from_file(params_file)
    return params


@log_on_entry
def fiducials(chip_type: int):
    fiducial_list: list | None = None
    if chip_type in [ChipType.Oxford, ChipType.OxfordInner, ChipType.Minichip]:
        fiducial_list = []
    elif chip_type == ChipType.Custom:
        # No fiducial for custom
        SSX_LOGGER.warning("No fiducials for custom chip")
    else:
        SSX_LOGGER.warning(f"Unknown chip_type, {chip_type}, in fiducials")
    return fiducial_list


def get_xy(addr: str, chip_type: ChipType):
    entry = addr.split("_")[-2:]
    R, C = entry[0][0], entry[0][1]
    r2, c2 = entry[1][0], entry[1][1]
    blockR = string.ascii_uppercase.index(R)
    blockC = int(C) - 1
    lowercase_list = list(string.ascii_lowercase + string.ascii_uppercase + "0")
    windowR = lowercase_list.index(r2)
    windowC = lowercase_list.index(c2)

    chip_params = get_chip_format(chip_type)

    x = (
        (blockC * chip_params.b2b_horz)
        + (blockC * (chip_params.x_num_steps - 1) * chip_params.x_step_size)
        + (windowC * chip_params.x_step_size)
    )
    y = (
        (blockR * chip_params.b2b_vert)
        + (blockR * (chip_params.y_num_steps - 1) * chip_params.y_step_size)
        + (windowR * chip_params.y_step_size)
    )
    return x, y


def pathli(l_in=None, way="typewriter", reverse=False):
    if l_in is None:
        l_in = []
    if reverse is True:
        li = list(reversed(l_in))
    else:
        li = list(l_in)
    long_list = []
    if li:
        if way == "typewriter":
            for i in range(len(li) ** 2):
                long_list.append(li[i % len(li)])
        elif way == "snake":
            lr = list(reversed(li))
            for rep in range(len(li)):
                if rep % 2 == 0:
                    long_list += li
                else:
                    long_list += lr
        elif way == "snake53":
            lr = list(reversed(li))
            for rep in range(53):
                if rep % 2 == 0:
                    long_list += li
                else:
                    long_list += lr
        elif way == "expand":
            for entry in li:
                for _ in range(len(li)):
                    long_list.append(entry)
        elif way == "expand28":
            for entry in li:
                for _ in range(28):
                    long_list.append(entry)
        elif way == "expand25":
            for entry in li:
                for _ in range(25):
                    long_list.append(entry)
        else:
            SSX_LOGGER.warning(f"No known path, way =  {way}")
    else:
        SSX_LOGGER.warning("No list written")
    return long_list


def zippum(list_1_args, list_2_args):
    list_1, type_1, reverse_1 = list_1_args
    list_2, type_2, reverse_2 = list_2_args
    A_path = pathli(list_1, type_1, reverse_1)
    B_path = pathli(list_2, type_2, reverse_2)
    zipped_list = []
    for a, b in zip(A_path, B_path, strict=False):
        zipped_list.append(a + b)
    return zipped_list


def get_alphanumeric(chip_type: ChipType):
    cell_format = get_chip_format(chip_type)
    blk_num = cell_format.x_blocks
    wnd_num = cell_format.x_num_steps
    uppercase_list = list(string.ascii_uppercase)[:blk_num]
    lowercase_list = list(string.ascii_lowercase + string.ascii_uppercase + "0")[
        :wnd_num
    ]
    number_list = [str(x) for x in range(1, blk_num + 1)]

    block_list = zippum([uppercase_list, "expand", 0], [number_list, "typewriter", 0])
    window_list = zippum(
        [lowercase_list, "expand", 0], [lowercase_list, "typewriter", 0]
    )

    alphanumeric_list = []
    for block in block_list:
        for window in window_list:
            alphanumeric_list.append(block + "_" + window)
    SSX_LOGGER.info(f"Length of alphanumeric list = {len(alphanumeric_list)}")
    return alphanumeric_list


@log_on_entry
def get_shot_order(chip_type: ChipType):
    cell_format = get_chip_format(chip_type)
    blk_num = cell_format.x_blocks
    wnd_num = cell_format.x_num_steps
    uppercase_list = list(string.ascii_uppercase)[:blk_num]
    number_list = [str(x) for x in range(1, blk_num + 1)]
    lowercase_list = list(string.ascii_lowercase + string.ascii_uppercase + "0")[
        :wnd_num
    ]

    block_list = zippum([uppercase_list, "snake", 0], [number_list, "expand", 0])
    window_dn = zippum([lowercase_list, "expand", 0], [lowercase_list, "snake", 0])
    window_up = zippum([lowercase_list, "expand", 1], [lowercase_list, "snake", 0])

    switch = 0
    count = 0
    collect_list = []
    for block in block_list:
        if switch == 0:
            for window in window_dn:
                collect_list.append(block + "_" + window)
            count += 1
            if count == blk_num:
                count = 0
                switch = 1
        else:
            for window in window_up:
                collect_list.append(block + "_" + window)
            count += 1
            if count == blk_num:
                count = 0
                switch = 0

    SSX_LOGGER.info(f"Length of collect list = {len(collect_list)}")
    return collect_list


@log_on_entry
def write_file(
    location: str = "i24",
    suffix: str = ".addr",
    order: str = "alphanumeric",
    param_file_path: Path = PARAM_FILE_PATH_FT,
    save_path: Path = HEADER_FILES_PATH,
):
    if location == "i24":
        params = read_parameter_file(param_file_path)
    else:
        msg = f"Unknown location, {location}"
        SSX_LOGGER.error(msg)
        raise ValueError(msg)
    chip_file_path = save_path / f"chips/{params.directory}/{params.filename}{suffix}"

    fiducial_list = fiducials(params.chip.chip_type.value)

    if order == "alphanumeric":
        addr_list = get_alphanumeric(params.chip.chip_type)
    elif order == "shot":
        addr_list = get_shot_order(params.chip.chip_type)
    else:
        raise ValueError(f"{order=} unrecognised")

    with open(chip_file_path, "a") as g:
        for addr in addr_list:
            xtal_name = "_".join([params.filename, addr])
            (x, y) = get_xy(xtal_name, params.chip.chip_type)
            if addr in fiducial_list:
                pres = "0"
            else:
                if "rand" in suffix:
                    pres = str(np.random.randint(2))
                else:
                    pres = "-1"
            line = "\t".join([xtal_name, str(x), str(y), "0.0", pres]) + "\n"
            g.write(line)

    SSX_LOGGER.info(f"Write {chip_file_path} completed")


@log_on_entry
def check_files(
    location: str,
    suffix_list: list[str],
    param_file_path: Path | str = PARAM_FILE_PATH_FT,
    save_path: Path = HEADER_FILES_PATH,
):
    if location == "i24":
        params = read_parameter_file(param_file_path)
    else:
        msg = f"Unknown location, {location}"
        SSX_LOGGER.error(msg)
        raise ValueError(msg)
    chip_file_path = save_path / f"chips/{params.directory}/{params.filename}"

    try:
        os.stat(chip_file_path)
    except Exception:
        os.makedirs(chip_file_path)
    for suffix in suffix_list:
        full_fid = chip_file_path.with_suffix(suffix)
        if full_fid.is_file():
            time_str = time.strftime("%Y%m%d_%H%M%S_")
            timestamp_fid = (  # noqa: F841
                full_fid.parent / f"{time_str}_{params.filename}{full_fid.suffix}"
            )
            # FIXME hack / fix. Actually move the file
            SSX_LOGGER.info(f"File {full_fid} Already Exists")
    SSX_LOGGER.debug("Check files done")
    return 1


@log_on_entry
def write_headers(
    location: str,
    suffix_list: list[str],
    param_file_path: Path = PARAM_FILE_PATH_FT,
    save_path: Path = HEADER_FILES_PATH,
):
    if location == "i24":
        params = read_parameter_file(param_file_path)
        chip_file_path = save_path / f"chips/{params.directory}/{params.filename}"

        for suffix in suffix_list:
            full_fid = chip_file_path.with_suffix(suffix)
            with open(full_fid, "w") as g:
                g.write(
                    "#23456789012345678901234567890123456789012345678901234567890123456789012345678901234567890\n#\n"
                )
                g.write(f"#&i24\tchip_name    = {params.filename}\n")
                g.write(f"#&i24\tvisit        = {params.visit}\n")
                g.write(f"#&i24\tsub_dir      = {params.directory}\n")
                g.write(f"#&i24\tn_exposures  = {params.num_exposures}\n")
                g.write(f"#&i24\tchip_type    = {params.chip.chip_type.value}\n")
                g.write(f"#&i24\tmap_type     = {params.map_type.value}\n")
                g.write(f"#&i24\tpump_repeat  = {params.pump_repeat.value}\n")
                g.write(f"#&i24\tpumpexptime  = {params.laser_dwell_s}\n")
                g.write(f"#&i24\texptime      = {params.laser_delay_s}\n")
                g.write(f"#&i24\tdcdetdist    = {params.detector_distance_mm}\n")
                g.write(f"#&i24\tprepumpexptime  = {params.pre_pump_exposure_s}\n")
                g.write(f"#&i24\tdet_Type     = {params.detector_name}\n")
                g.write("#\n")
                g.write(
                    "#XtalAddr      XCoord  YCoord  ZCoord  Present Shot  Spare04 Spare03 Spare02 Spare01\n"
                )
    else:
        msg = f"Unknown location, {location}"
        SSX_LOGGER.error(msg)
        raise ValueError(msg)
    SSX_LOGGER.debug("Write headers done")


def run():
    SSX_LOGGER.debug("Run Startup")
    check_files("i24", [".addr", ".shot"])
    SSX_LOGGER.info("Checked Files")
    write_headers("i24", [".addr", ".shot"])
    SSX_LOGGER.info("Written Headers")
    SSX_LOGGER.info("Writing to Files has been disabled. Headers Only")
    # Makes a file with random crystal positions
    check_files("i24", ["rando.spec"])
    write_headers("i24", ["rando.spec"])
    SSX_LOGGER.debug("StartUp Done")


if __name__ == "__main__":
    run()
