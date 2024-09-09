"""
Move on click gui for fixed targets at I24
Robin Owen 12 Jan 2021
"""

import logging
from collections.abc import Sequence

import bluesky.plan_stubs as bps
import cv2 as cv
from bluesky.run_engine import RunEngine
from dodal.beamlines import i24
from dodal.devices.i24.pmac import PMAC
from dodal.devices.oav.oav_detector import OAV

from mx_bluesky.beamlines.i24.serial.fixed_target import (
    i24ssx_Chip_Manager_py3v1 as manager,
)
from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import Fiducials
from mx_bluesky.beamlines.i24.serial.parameters.constants import OAV1_CAM

logger = logging.getLogger("I24ssx.moveonclick")


def _get_beam_centre(oav: OAV):
    """Extract the beam centre x/y positions from the display.configuration file.

    Args:
        oav (OAV): the OAV device.
    """
    return oav.parameters.beam_centre_i, oav.parameters.beam_centre_j


def _calculate_zoom_calibrator(oav: OAV):
    """Set the scale for the zoom calibrator for the pmac moves."""
    currentzoom = yield from bps.rd(oav.zoom_controller.percentage)
    zoomcalibrator = 1.547 - (0.03 * currentzoom) + (0.0001634 * currentzoom**2)
    return zoomcalibrator


def _move_on_mouse_click_plan(
    oav: OAV, pmac: PMAC, beam_centre: Sequence[int], clicked_position: Sequence[int]
):
    """A plan that calculates the zoom calibrator and moves to the clicked \
        position coordinates.
    """
    zoomcalibrator = yield from _calculate_zoom_calibrator(oav)
    beamX, beamY = beam_centre
    x, y = clicked_position
    xmove = -1 * (beamX - x) * zoomcalibrator
    ymove = -1 * (beamY - y) * zoomcalibrator
    logger.info(f"Moving X and Y {xmove} {ymove}")
    xmovepmacstring = "#1J:" + str(xmove)
    ymovepmacstring = "#2J:" + str(ymove)
    yield from bps.abs_set(pmac.pmac_string, xmovepmacstring, wait=True)
    yield from bps.abs_set(pmac.pmac_string, ymovepmacstring, wait=True)


# Register clicks and move chip stages
def onMouse(event, x, y, flags, param):
    if event == cv.EVENT_LBUTTONUP:
        RE = param[0]
        pmac = param[1]
        oav = param[2]
        beamX, beamY = _get_beam_centre(oav)
        logger.info(f"Clicked X and Y {x} {y}")
        RE(_move_on_mouse_click_plan(oav, pmac, (beamX, beamY), (x, y)))


def update_ui(oav, frame):
    # Get beam x and y values
    beamX, beamY = _get_beam_centre(oav)

    # Overlay text and beam centre
    cv.ellipse(
        frame, (beamX, beamY), (12, 8), 0.0, 0.0, 360, (0, 255, 255), thickness=2
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


def start_viewer(oav: OAV, pmac: PMAC, RE: RunEngine, oav1: str = OAV1_CAM):
    # Create a video caputure from OAV1
    cap = cv.VideoCapture(oav1)

    # Create window named OAV1view and set onmouse to this
    cv.namedWindow("OAV1view")
    cv.setMouseCallback("OAV1view", onMouse, param=[RE, pmac, oav])  # type: ignore

    logger.info("Showing camera feed. Press escape to close")
    # Read captured video and store them in success and frame
    success, frame = cap.read()

    # Loop until escape key is pressed. Keyboard shortcuts here
    while success:
        success, frame = cap.read()

        update_ui(oav, frame)

        k = cv.waitKey(1)
        if k == 113:  # Q
            RE(manager.moveto(Fiducials.zero, pmac))
        if k == 119:  # W
            RE(manager.moveto(Fiducials.fid1, pmac))
        if k == 101:  # E
            RE(manager.moveto(Fiducials.fid2, pmac))
        if k == 97:  # A
            RE(bps.trigger(pmac.home, wait=True))
            print("Current position set as origin")
        if k == 115:  # S
            RE(manager.fiducial(1))
        if k == 100:  # D
            RE(manager.fiducial(2))
        if k == 99:  # C
            RE(manager.cs_maker(pmac))
        if k == 98:  # B
            RE(
                manager.block_check()
            )  # doesn't work well for blockcheck as image doesn't update
        if k == 104:  # H
            RE(bps.abs_set(pmac.pmac_string, "#2J:-10", wait=True))
        if k == 110:  # N
            RE(bps.abs_set(pmac.pmac_string, "#2J:10", wait=True))
        if k == 109:  # M
            RE(bps.abs_set(pmac.pmac_string, "#1J:-10", wait=True))
        if k == 98:  # B
            RE(bps.abs_set(pmac.pmac_string, "#1J:10", wait=True))
        if k == 105:  # I
            RE(bps.abs_set(pmac.pmac_string, "#3J:-150", wait=True))
        if k == 111:  # O
            RE(bps.abs_set(pmac.pmac_string, "#3J:150", wait=True))
        if k == 117:  # U
            RE(bps.abs_set(pmac.pmac_string, "#3J:-1000", wait=True))
        if k == 112:  # P
            RE(bps.abs_set(pmac.pmac_string, "#3J:1000", wait=True))
        if k == 0x1B:  # esc
            cv.destroyWindow("OAV1view")
            print("Pressed escape. Closing window")
            break

    # Clear cameraCapture instance
    cap.release()


if __name__ == "__main__":
    RE = RunEngine()
    # Get devices out of dodal
    oav: OAV = i24.oav()
    pmac: PMAC = i24.pmac()
    start_viewer(oav, pmac, RE)