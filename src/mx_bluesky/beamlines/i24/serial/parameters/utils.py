from typing import Any

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import ChipType
from mx_bluesky.beamlines.i24.serial.parameters.experiment_parameters import (
    ChipDescription,
)
from mx_bluesky.beamlines.i24.serial.setup_beamline import caget, pv

OXFORD_BLOCKS_PVS = [f"ME14E-MO-IOC-01:GP{i}" for i in range(11, 75)]


class EmptyMapError(Exception):
    pass


def get_chip_format(chip_type: ChipType) -> ChipDescription:
    """Default parameter values."""
    defaults: dict[str, int | float] = {}
    match chip_type:
        case ChipType.Oxford:
            defaults["x_num_steps"] = defaults["y_num_steps"] = 20
            defaults["x_step_size"] = defaults["y_step_size"] = 0.125
            defaults["x_blocks"] = defaults["y_blocks"] = 8
            defaults["b2b_horz"] = defaults["b2b_vert"] = 0.800
        case ChipType.OxfordInner:
            defaults["x_num_steps"] = defaults["y_num_steps"] = 25
            defaults["x_step_size"] = defaults["y_step_size"] = 0.600
            defaults["x_blocks"] = defaults["y_blocks"] = 1
            defaults["b2b_horz"] = defaults["b2b_vert"] = 0.0
        case ChipType.Minichip:
            defaults["x_num_steps"] = defaults["y_num_steps"] = 20
            defaults["x_step_size"] = defaults["y_step_size"] = 0.125
            defaults["x_blocks"] = defaults["y_blocks"] = 1
            defaults["b2b_horz"] = defaults["b2b_vert"] = 0.0
        case ChipType.Custom:
            defaults["x_num_steps"] = int(caget(pv.me14e_gp6))
            defaults["y_num_steps"] = int(caget(pv.me14e_gp7))
            defaults["x_step_size"] = float(caget(pv.me14e_gp8))
            defaults["y_step_size"] = float(caget(pv.me14e_gp99))
            defaults["x_blocks"] = defaults["y_blocks"] = 1
            defaults["b2b_horz"] = defaults["b2b_vert"] = 0.0
        case ChipType.MISP:
            defaults["x_num_steps"] = defaults["y_num_steps"] = 78
            defaults["x_step_size"] = defaults["y_step_size"] = 0.1193
            defaults["x_blocks"] = defaults["y_blocks"] = 1
            defaults["b2b_horz"] = defaults["b2b_vert"] = 0.0
    chip_params: dict[str, Any] = {"chip_type": chip_type, **defaults}
    return ChipDescription(**chip_params)


def get_chip_map() -> list[int]:
    """Return a list of blocks (the 'chip map') to be collected on an Oxford type chip \
        when using lite mapping."""
    chipmap = []
    for n, block_pv in enumerate(OXFORD_BLOCKS_PVS):
        block_val = int(caget(block_pv))
        if block_val == 1:
            chipmap.append(n + 1)
    if len(chipmap) == 0:
        raise EmptyMapError("No blocks selected for Lite map.")
    return chipmap
