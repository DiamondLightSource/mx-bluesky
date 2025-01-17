from collections.abc import Sequence
from typing import Literal

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from blueapi.core import MsgGenerator
from dodal.beamlines import i24

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
from mx_bluesky.beamlines.i24.serial.setup_beamline import pv
from mx_bluesky.beamlines.i24.serial.setup_beamline.ca import caput
from mx_bluesky.beamlines.i24.serial.setup_beamline.pv_abstract import Eiger, Pilatus
from mx_bluesky.beamlines.i24.serial.setup_beamline.setup_detector import (
    _move_detector_stage,
    get_detector_type,
)


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


@bpp.run_decorator()
def gui_sleep(sec: int) -> MsgGenerator:
    for _ in range(sec):
        yield from bps.sleep(1)


@bpp.run_decorator()
def gui_move_detector(det: Literal["eiger", "pilatus"]) -> MsgGenerator:
    detector_stage = i24.detector_motion()
    det_y_target = Eiger.det_y_target if det == "eiger" else Pilatus.det_y_target
    yield from _move_detector_stage(detector_stage, det_y_target)
    caput(pv.me14e_gp101, det)


@bpp.run_decorator()
def gui_use_jungfrau() -> MsgGenerator:
    print("Set to use jungfrau detector")
    caput(pv.me14e_gp101, "jungfrau")
    yield from bps.null()


@bpp.run_decorator()
def gui_set_parameters(
    sub_dir: str,
    chip_name: str,
    exp_time: float,
    det_dist: float,
    transmission: float,
    n_shots: int,
    chip_type: str,
    pump_settings: Sequence,
    use_mapping_lite: bool,
    chipmap: Sequence = (),
):
    detector_stage = i24.detector_motion()
    det_type = yield from get_detector_type(detector_stage)
    chip_params = get_chip_format(ChipType[chip_type])
    pump_repeat = (
        PumpProbeSetting.NoPP
        if not pump_settings[0]
        else PumpProbeSetting[pump_settings[0]]
    )
    map_type = MappingType.Lite if use_mapping_lite else MappingType.NoMap

    if chip_params.chip_type is ChipType.Oxford:
        if use_mapping_lite and len(chipmap) == 0:
            raise ValueError("Mapping lite chosen but no chipmap")

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
        "map_type": map_type,
        "chip_map": list(chipmap),
        "pump_repeat": pump_repeat,
        "laser_dwell_s": pump_settings[1]
        if pump_repeat != PumpProbeSetting.NoPP
        else 0.0,
        "laser_delay_s": pump_settings[2]
        if pump_repeat != PumpProbeSetting.NoPP
        else 0.0,
        "checker_pattern": pump_settings[3],
        "pre_pump_exposure_s": None,
    }
    # At some point it will use FixedTargetParameters to create the parameters model
    # For now not doing that because:
    # a- not all data in
    print(FixedTargetParameters(**params))
    yield from bps.sleep(0.5)
