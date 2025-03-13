# from collections.abc import Sequence
from typing import Literal

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from blueapi.core import MsgGenerator
from dodal.beamlines import i24
from dodal.devices.i24.dual_backlight import BacklightPositions

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import (
    ChipType,
    MappingType,
    PumpProbeSetting,
)
from mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_moveonclick import (
    _move_on_mouse_click_plan,
)
from mx_bluesky.beamlines.i24.serial.log import _read_visit_directory_from_file
from mx_bluesky.beamlines.i24.serial.parameters import (
    FixedTargetParameters,
    get_chip_format,
)
from mx_bluesky.beamlines.i24.serial.parameters.utils import EmptyMapError
from mx_bluesky.beamlines.i24.serial.setup_beamline import pv
from mx_bluesky.beamlines.i24.serial.setup_beamline.ca import caput
from mx_bluesky.beamlines.i24.serial.setup_beamline.pv_abstract import Eiger, Pilatus
from mx_bluesky.beamlines.i24.serial.setup_beamline.setup_detector import (
    _move_detector_stage,
    get_detector_type,
)


@bpp.run_decorator()
def gui_move_backlight(position: str) -> MsgGenerator:
    backlight = i24.backlight()
    bl_pos = BacklightPositions(position)
    yield from bps.abs_set(backlight, bl_pos, wait=True)


@bpp.run_decorator()
def gui_stage_move_on_click(position_px: tuple[int, int]) -> MsgGenerator:
    oav = i24.oav()
    pmac = i24.pmac()
    yield from _move_on_mouse_click_plan(oav, pmac, position_px)


@bpp.run_decorator()
def gui_gonio_move_on_click(position_px: tuple[int, int]) -> MsgGenerator:
    oav = i24.oav()
    gonio = i24.vgonio()

    x_pixels_per_micron = yield from bps.rd(oav.microns_per_pixel_x)
    y_pixels_per_micron = yield from bps.rd(oav.microns_per_pixel_y)

    x_um = position_px[0] * x_pixels_per_micron
    y_um = position_px[1] * y_pixels_per_micron

    # gonio is in mm?
    yield from bps.mv(gonio.x, x_um / 1000, gonio.yh, y_um / 1000)  # type: ignore


# See https://github.com/DiamondLightSource/mx-bluesky/issues/853
@bpp.run_decorator()
def gui_sleep(sec: int) -> MsgGenerator:
    for _ in range(sec):
        yield from bps.sleep(1)


@bpp.run_decorator()
def gui_move_detector(det: Literal["eiger", "pilatus"]) -> MsgGenerator:
    detector_stage = i24.detector_motion()
    det_y_target = Eiger.det_y_target if det == "eiger" else Pilatus.det_y_target
    yield from _move_detector_stage(detector_stage, det_y_target)
    # Make the output readable
    caput(pv.me14e_gp101, det)


@bpp.run_decorator()
def gui_set_parameters(
    sub_dir: str,
    chip_name: str,
    exp_time: float,
    det_dist: float,
    transmission: float,
    n_shots: int,
    chip_type: str,
    map_type: str,
    chip_format: list[int | float],  # for Lite Oxford it's the chipmap
    checker_pattern: bool,
    pump_probe: str,
    laser_dwell: float,
    laser_delay: float,
    pre_pump: float,
) -> MsgGenerator:
    # NOTE still a work in progress, adding to it as the ui grows
    detector_stage = i24.detector_motion()
    det_type = yield from get_detector_type(detector_stage)
    _format = chip_format if ChipType[chip_type] is ChipType.Custom else None
    chip_params = get_chip_format(ChipType[chip_type], _format)
    if ChipType[chip_type] in [ChipType.Oxford, ChipType.OxfordInner]:
        mapping = MappingType.Lite if map_type == "Lite" else MappingType.NoMap
        if mapping is MappingType.Lite and len(chip_format) == 0:
            # this logic should go in the gui with error message.
            raise EmptyMapError("No blocks chosen")
        chip_map = chip_format
    else:
        mapping = MappingType.NoMap
        chip_map = []

    params = {
        "visit": _read_visit_directory_from_file().as_posix(),  # noqa
        "directory": sub_dir,
        "filename": chip_name,
        "exposure_time_s": exp_time,
        "detector_distance_mm": det_dist,
        "detector_name": str(det_type),
        "num_exposures": n_shots,
        "transmission": transmission,
        "chip": chip_params,
        "map_type": mapping,
        "chip_map": chip_map,
        "pump_repeat": PumpProbeSetting[pump_probe],  # pump_repeat,
        "laser_dwell_s": laser_dwell,
        "laser_delay_s": laser_delay,
        "checker_pattern": checker_pattern,
        "pre_pump_exposure_s": pre_pump,
    }
    # This will then run the run_fixed_target plan
    yield from bps.sleep(0.5)
    return FixedTargetParameters(**params)
