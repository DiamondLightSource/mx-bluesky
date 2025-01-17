from datetime import datetime
from enum import Enum
from pathlib import Path

from bluesky.plan_stubs import abs_set, rd, sleep
from dodal.devices.i24.i24_vgonio import VGonio
from dodal.devices.zebra import Zebra

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.jungfrau_plans import (
    setup_detector,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.zebra_plans import (
    setup_zebra_for_darks,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils import run_number
from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.jf_commissioning_devices import (
    JungfrauM1,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.log import LOGGER
from mx_bluesky.beamlines.i24.serial.setup_beamline.setup_zebra_plans import arm_zebra


class GainMode(str, Enum):
    dynamic = "dynamic"
    forceswitchg1 = "forceswitchg1"
    forceswitchg2 = "forceswitchg2"


def date_time_string():
    return datetime.now().strftime("%Y-%m-%d-%H-%M-%s")


def set_gain_mode(
    jungfrau: JungfrauM1, gain_mode: GainMode, wait=True, check_for_errors=True
):
    LOGGER.info(f"Setting gain mode {gain_mode.value}")
    yield from abs_set(jungfrau.gain_mode, gain_mode.value, wait=wait)
    if check_for_errors:
        err: str = yield from rd(jungfrau.error_rbv)  # type: ignore
        LOGGER.warn(f"JF reporting error: {err}")


def do_dark_acquisition(
    jungfrau: JungfrauM1, zebra: Zebra, gonio: VGonio, exp_time_s, acq_time_s, n_frames
):
    LOGGER.info("Setting up detector")
    yield from setup_detector(jungfrau, exp_time_s, acq_time_s, n_frames, wait=True)
    yield from abs_set(VGonio.omega, 0, wait=True)
    LOGGER.info("Setting up and arming zebra")
    yield from setup_zebra_for_darks(zebra, wait=True)
    yield from abs_set(arm_zebra(zebra), wait=True)
    LOGGER.info("Triggering collection")
    yield from abs_set(VGonio.omega, 1, wait=True)
    yield from abs_set(jungfrau.acquire_start, 1)
    yield from sleep(exp_time_s * n_frames)


def do_darks(
    jungfrau: JungfrauM1,
    zebra: Zebra,
    gonio: VGonio,
    directory: str = "/tmp/",
    check_for_errors=True,
):
    directory_prefix = Path(directory) / f"{run_number(Path(directory))}_darks"

    # Gain 0
    yield from set_gain_mode(
        jungfrau, GainMode.dynamic, check_for_errors=check_for_errors
    )
    yield from abs_set(
        jungfrau.file_directory,
        (directory_prefix / "G0").as_posix(),
    )
    yield from do_dark_acquisition(jungfrau, zebra, gonio, 0.001, 0.001, 1000)

    # Gain 1
    yield from set_gain_mode(
        jungfrau, GainMode.forceswitchg1, check_for_errors=check_for_errors
    )
    yield from abs_set(
        jungfrau.file_directory,
        (directory_prefix / "G1").as_posix(),
    )
    yield from do_dark_acquisition(jungfrau, zebra, gonio, 0.001, 0.01, 1000)

    # Gain 2
    yield from set_gain_mode(
        jungfrau, GainMode.forceswitchg2, check_for_errors=check_for_errors
    )
    yield from abs_set(
        jungfrau.file_directory,
        (directory_prefix / "G2").as_posix(),
    )
    yield from do_dark_acquisition(jungfrau, zebra, gonio, 0.001, 0.01, 1000)
