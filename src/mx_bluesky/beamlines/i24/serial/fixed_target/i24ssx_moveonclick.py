"""
Move on click gui for fixed targets at I24
Robin Owen 12 Jan 2021
"""

from collections.abc import Sequence

import bluesky.plan_stubs as bps
import cv2 as cv
from bluesky.run_engine import RunEngine
from dodal.beamlines import i24
from dodal.devices.i24.pmac import PMAC
from dodal.devices.oav.oav_detector import OAV

from mx_bluesky.beamlines.i24.serial.fixed_target import (
    i24ssx_chip_manager_py3v1 as manager,
)
from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import Fiducials
from mx_bluesky.beamlines.i24.serial.log import SSX_LOGGER
from mx_bluesky.beamlines.i24.serial.parameters.constants import OAV1_CAM


def _get_beam_centre(oav: OAV):
    """Extract the beam centre x/y positions from the display.configuration file.

    Args:
        oav (OAV): the OAV device.
    """
    beam_x = yield from bps.rd(oav.beam_centre_i)
    beam_y = yield from bps.rd(oav.beam_centre_j)
    return beam_x, beam_y


def _calculate_zoom_calibrator(oav: OAV):
    """Set the scale for the zoom calibrator for the pmac moves."""
    currentzoom = yield from bps.rd(oav.zoom_controller.percentage)
    zoomcalibrator = (
        1.285
        - (0.02866 * currentzoom)
        + (0.00025 * currentzoom**2)
        - (0.0000008151 * currentzoom**3)
    )
    return zoomcalibrator


def _move_on_mouse_click_plan(
    oav: OAV,
    pmac: PMAC,
    clicked_position: Sequence[int],
):
    """A plan that calculates the zoom calibrator and moves to the clicked \
        position coordinates.
    """
    zoomcalibrator = yield from _calculate_zoom_calibrator(oav)
    beam_x, beam_y = yield from _get_beam_centre(oav)
    x, y = clicked_position
    xmove = -10 * (beam_x - x) * zoomcalibrator
    ymove = 10 * (beam_y - y) * zoomcalibrator
    SSX_LOGGER.info(f"Zoom calibrator {zoomcalibrator}")
    SSX_LOGGER.info(f"Beam centre {beam_x} {beam_y}")
    SSX_LOGGER.info(f"Moving X and Y {xmove} {ymove}")
    xmovepmacstring = "&2#5J:" + str(xmove)
    ymovepmacstring = "&2#6J:" + str(ymove)
    yield from bps.abs_set(pmac.pmac_string, xmovepmacstring, wait=True)
    yield from bps.abs_set(pmac.pmac_string, ymovepmacstring, wait=True)


# Register clicks and move chip stages
def on_mouse(event, x, y, flags, param):
    if event == cv.EVENT_LBUTTONUP:
        run_engine = param[0]
        pmac = param[1]
        oav = param[2]
        SSX_LOGGER.info(f"Clicked X and Y {x} {y}")
        run_engine(_move_on_mouse_click_plan(oav, pmac, (x, y)))


def update_ui(oav, frame, run_engine):
    # Get beam x and y values
    beam_x, beam_y = run_engine(_get_beam_centre(oav)).plan_result

    # Overlay text and beam centre
    cv.ellipse(
        frame, (beam_x, beam_y), (12, 8), 0.0, 0.0, 360, (0, 255, 255), thickness=2
    )
    cv.putText(
        frame,
        "Key bindings",
        (20, 40),
        cv.FONT_HERSHEY_COMPLEX_SMALL,
        1,
        (0, 255, 255),
        1,
        1,
    )
    cv.putText(
        frame,
        "Q / A : go to / set as f0",
        (25, 70),
        cv.FONT_HERSHEY_COMPLEX_SMALL,
        0.8,
        (0, 255, 255),
        1,
        1,
    )
    cv.putText(
        frame,
        "W / S : go to / set as f1",
        (25, 90),
        cv.FONT_HERSHEY_COMPLEX_SMALL,
        0.8,
        (0, 255, 255),
        1,
        1,
    )
    cv.putText(
        frame,
        "E / D : go to / set as f2",
        (25, 110),
        cv.FONT_HERSHEY_COMPLEX_SMALL,
        0.8,
        (0, 255, 255),
        1,
        1,
    )
    cv.putText(
        frame,
        "I / O : in /out of focus",
        (25, 130),
        cv.FONT_HERSHEY_COMPLEX_SMALL,
        0.8,
        (0, 255, 255),
        1,
        1,
    )
    cv.putText(
        frame,
        "C : Create CS",
        (25, 150),
        cv.FONT_HERSHEY_COMPLEX_SMALL,
        0.8,
        (0, 255, 255),
        1,
        1,
    )
    cv.putText(
        frame,
        "esc : close window",
        (25, 170),
        cv.FONT_HERSHEY_COMPLEX_SMALL,
        0.8,
        (0, 255, 255),
        1,
        1,
    )
    cv.imshow("OAV1view", frame)


def start_viewer(oav: OAV, pmac: PMAC, run_engine: RunEngine, oav1: str = OAV1_CAM):
    # Create a video capture from OAV1
    cap = cv.VideoCapture(oav1)

    # Create window named OAV1view and set onmouse to this
    cv.namedWindow("OAV1view")
    cv.setMouseCallback("OAV1view", on_mouse, param=[run_engine, pmac, oav])  # type: ignore

    SSX_LOGGER.info("Showing camera feed. Press escape to close")
    # Read captured video and store them in success and frame
    success, frame = cap.read()

    # Loop until escape key is pressed. Keyboard shortcuts here
    while success:
        success, frame = cap.read()

        update_ui(oav, frame, run_engine)

        k = cv.waitKey(1)
        if k == 113:  # Q
            run_engine(manager.moveto(Fiducials.zero, pmac))
        if k == 119:  # W
            run_engine(manager.moveto(Fiducials.fid1, pmac))
        if k == 101:  # E
            run_engine(manager.moveto(Fiducials.fid2, pmac))
        if k == 97:  # A
            run_engine(bps.trigger(pmac.home, wait=True))
            print("Current position set as origin")
        if k == 115:  # S
            run_engine(manager.fiducial(1))
        if k == 100:  # D
            run_engine(manager.fiducial(2))
        if k == 99:  # C
            run_engine(manager.cs_maker(pmac))
        if k == 98:  # B
            run_engine(
                manager.block_check()
            )  # doesn't work well for blockcheck as image doesn't update
        if k == 104:  # H
            run_engine(bps.abs_set(pmac.pmac_string, "&2#6J:-10", wait=True))
        if k == 110:  # N
            run_engine(bps.abs_set(pmac.pmac_string, "&2#6J:10", wait=True))
        if k == 109:  # M
            run_engine(bps.abs_set(pmac.pmac_string, "&2#5J:-10", wait=True))
        if k == 98:  # B
            run_engine(bps.abs_set(pmac.pmac_string, "&2#5J:10", wait=True))
        if k == 105:  # I
            run_engine(bps.abs_set(pmac.pmac_string, "&2#7J:-150", wait=True))
        if k == 111:  # O
            run_engine(bps.abs_set(pmac.pmac_string, "&2#7J:150", wait=True))
        if k == 117:  # U
            run_engine(bps.abs_set(pmac.pmac_string, "&2#7J:-1000", wait=True))
        if k == 112:  # P
            run_engine(bps.abs_set(pmac.pmac_string, "&2#7J:1000", wait=True))
        if k == 0x1B:  # esc
            cv.destroyWindow("OAV1view")
            print("Pressed escape. Closing window")
            break

    # Clear cameraCapture instance
    cap.release()


if __name__ == "__main__":
    run_engine = RunEngine(call_returns_result=True)
    # Get devices out of dodal
    oav: OAV = i24.oav(connect_immediately=True)
    pmac: PMAC = i24.pmac(connect_immediately=True)
    start_viewer(oav, pmac, run_engine)
