"""
Startup utilities for chip
"""

import string

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import ChipType
from mx_bluesky.beamlines.i24.serial.log import SSX_LOGGER, log_on_entry
from mx_bluesky.beamlines.i24.serial.parameters import get_chip_format


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
