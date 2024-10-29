"""
Chip mapping utilities for fixed target

This version changed to python3 March2020 by RLO
"""

import logging
import time

import numpy as np

from mx_bluesky.beamlines.i24.serial import log
from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import ChipType
from mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_Chip_StartUp_py3v1 import (
    check_files,
    get_shot_order,
    get_xy,
    read_parameter_file,
    write_file,
)
from mx_bluesky.beamlines.i24.serial.parameters import get_chip_format
from mx_bluesky.beamlines.i24.serial.parameters.constants import PARAM_FILE_PATH_FT

logger = logging.getLogger("I24ssx.chip_mapping")


def setup_logging():
    # Log should now change name daily.
    logfile = time.strftime("i24_%Y_%m_%d.log").lower()
    log.config(logfile)


@log.log_on_entry
def read_file_make_dict(fid, chip_type, switch=False):
    a_dict = {}
    b_dict = {}
    with open(fid) as f:
        for line in f.readlines():
            if line.startswith("#"):
                continue
            else:
                entry = line.rstrip().split()
                addr = entry[0][-5:]
                pres = entry[4]
                x, y = get_xy(addr, chip_type)
                a_dict[x, y] = pres
                b_dict[addr] = pres
    if switch is True:
        return b_dict
    else:
        return a_dict


@log.log_on_entry
def plot_file(plt, fid, chip_type):
    chip_dict = read_file_make_dict(fid, chip_type)
    x_list, y_list, z_list = [], [], []
    for k in sorted(chip_dict.keys()):
        x, y = k[0], k[1]
        pres = chip_dict[k]
        x_list.append(float(x))
        y_list.append(float(y))
        z_list.append(float(pres))

    X = np.array(x_list)
    Y = np.array(y_list)
    Z = np.array(z_list)
    xr = X.ravel()
    yr = Y.ravel()
    zr = Z.ravel()

    fig = plt.figure(num=None, figsize=(12, 12), facecolor="0.6", edgecolor="k")
    fig.subplots_adjust(
        left=0.03, bottom=0.03, right=0.97, top=0.97, wspace=0, hspace=0
    )
    ax1 = fig.add_subplot(111, aspect="equal", axisbg="0.3")
    ax1.scatter(xr, yr, c=zr, s=8, alpha=1, marker="s", linewidth=0.1, cmap="winter")
    ax1.set_xlim(-1, 26)
    ax1.set_ylim(-1, 26)
    ax1.invert_yaxis()
    check_files("i24", [f"{chip_type}.png"])
    plt.savefig(f"{fid[:-5]}.png", dpi=200, bbox_inches="tight", pad_inches=0.05)
    return 1


@log.log_on_entry
def convert_chip_to_hex(fid, chip_type):
    chip_dict = read_file_make_dict(fid, chip_type, True)
    chip_format = get_chip_format(ChipType(chip_type))
    check_files("i24", [f"{chip_type}.full"])
    with open(f"{fid[:-5]}.full", "w") as g:
        # Normal
        if chip_type in [ChipType.Oxford, ChipType.OxfordInner]:
            shot_order_list = get_shot_order(chip_type)
            logger.info("Shot Order List: \n")
            logger.info(f"{shot_order_list[:14]}")
            logger.info(f"{shot_order_list[-14:]}")
            for i, k in enumerate(shot_order_list):
                if i % 20 == 0:
                    logger.info("\n")
                else:
                    logger.info(f"{k}")
            sorted_pres_list = []
            for addr in shot_order_list:
                sorted_pres_list.append(chip_dict[addr])

            windows_per_block = chip_format.x_num_steps
            number_of_lines = int(len(sorted_pres_list) / windows_per_block)
            hex_length = windows_per_block / 4
            pad = int(7 - hex_length)
            for i in range(number_of_lines):
                sublist = sorted_pres_list[
                    i * windows_per_block : (i * windows_per_block) + windows_per_block
                ]
                if i % 2 == 0:
                    right_list = sublist
                else:
                    right_list = sublist[::-1]
                hex_string = (f"{{0:0>{hex_length}X}}").format(
                    int("".join(str(x) for x in right_list), 2)
                )
                hex_string = hex_string + (pad * "0")
                pvar = 5001 + i
                line = f"P{pvar}=${hex_string}"
                g.write(line + "\n")
                logger.info("hex string: %s" % (hex_string + 4 * "0"))
                logger.info(f"line number= {i}")
                logger.info(
                    "right_list: \n{}\n".format("".join(str(x) for x in right_list))
                )
                logger.info(f"PVAR: {line}")
                if (i + 1) % windows_per_block == 0:
                    logger.info(
                        "\n %s" % (40 * (" %i" % ((i / windows_per_block) + 2)))
                    )
            logger.info(f"hex_length: {hex_length}")
        else:
            logger.warning("Chip type unknown, no conversion done.")
    return 0


def main(plt):
    setup_logging()
    params = read_parameter_file()

    check_files("i24", [".spec"])
    write_file(suffix=".spec", order="shot")

    logger.info(f"PARAMETER PATH = {PARAM_FILE_PATH_FT}")
    fid = PARAM_FILE_PATH_FT / f"{params.filename}.spec"
    logger.info(f"FID = {fid}")

    plot_file(plt, fid, params.chip.chip_type.value)
    convert_chip_to_hex(fid, params.chip.chip_type.value)


if __name__ == "__main__":
    from matplotlib import pyplot as plt

    main(plt)
    plt.show()
    plt.close()
