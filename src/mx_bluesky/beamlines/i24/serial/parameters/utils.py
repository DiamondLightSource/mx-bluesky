from collections.abc import Sequence
from typing import Any, Literal

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import ChipType
from mx_bluesky.beamlines.i24.serial.parameters.experiment_parameters import (
    ChipDescription,
)
from mx_bluesky.beamlines.i24.serial.setup_beamline import caget, pv

OXFORD_BLOCKS_PVS = [f"ME14E-MO-IOC-01:GP{i}" for i in range(11, 75)]


class EmptyMapError(Exception):
    pass


def get_chip_format(
    chip_type: ChipType,
    format: Sequence[int | float] | None = None,
    origin: Literal["edm", "web"] = "edm",
) -> ChipDescription:
    """Get the default parameter values for the requested chip type.

    For an Oxford-type chip, the default values are hard coded as the dimensions are
    always the same. For a Custom chip instead, the number of steps and step size in
    each direction must be entered through the GUI - web or edm. If the collection is
    run through the edm, the values will be read from the general purpose PVs set on
    there. If instead the plan is run from the web UI, the values will be passed in the
    form of a list/tuple of 4 values.

    Args:
        chip_type (ChipType): Chip in use
        custom_format (Sequence[int | float], optional): Number and size of steps input
            from the web ui. Format should be: [int, int, float, float].
            Defaults to None.
        origin (str, optional): UI in use, can be either web or edm. Defaults to edm.
    """
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
            if origin == "edm":
                defaults["x_num_steps"] = int(caget(pv.me14e_gp6))
                defaults["y_num_steps"] = int(caget(pv.me14e_gp7))
                defaults["x_step_size"] = float(caget(pv.me14e_gp8))
                defaults["y_step_size"] = float(caget(pv.me14e_gp99))
            else:
                # NOTE Test for WEB GUI
                if not format:
                    raise ValueError("Format for custom chip not passed")
                defaults["x_num_steps"] = format[0]
                defaults["y_num_steps"] = format[1]
                defaults["x_step_size"] = format[2]
                defaults["y_step_size"] = format[3]
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
