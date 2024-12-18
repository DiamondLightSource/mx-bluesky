from typing import Literal

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from blueapi.core import MsgGenerator
from dodal.beamlines import i24

from mx_bluesky.beamlines.i24.serial.fixed_target.i24ssx_moveonclick import (
    _move_on_mouse_click_plan,
)
from mx_bluesky.beamlines.i24.serial.log import _read_visit_directory_from_file
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


@bpp.run_decorator()
def gui_set_parameters(
    sub_dir: str,
    chip_name: str,
    exp_time: float,
    det_dist: float,
    transmission: float,
    n_shots: int,
):
    detector_stage = i24.detector_motion()
    det_type = yield from get_detector_type(detector_stage)
    params = {
        "visit": _read_visit_directory_from_file().as_posix(),  # noqa
        "directory": sub_dir,
        "filename": chip_name,
        "exposure_time_s": exp_time,
        "detector_distance_mm": det_dist,
        "detector_name": str(det_type),
        "num_exposures": n_shots,
        "transmission": transmission,
    }
    # At some point it will use FixedTargetParameters to create the parameters model
    # For now not doing that because:
    # a- not all data in
    # b - detectorParams will create a directory and we do not want that unless testing
    # on beamline
    # FixedTargetParameters(**params)
    print(params)
    yield from bps.sleep(0.5)
