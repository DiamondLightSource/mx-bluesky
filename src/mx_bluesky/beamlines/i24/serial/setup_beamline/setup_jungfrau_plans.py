import bluesky.plan_stubs as bps
from dodal.devices.i24.jungfrau import GainMode, JungFrau1M, TriggerMode

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.jungfrau_plans import (
    do_manual_acquisition,
)
from mx_bluesky.beamlines.i24.serial.log import SSX_LOGGER

DARK_MULTIPLIER = {"G0": 1, "G1": 10}


def setup_and_run_jungfrau_for_darks_plan(
    jungfrau: JungFrau1M,
    filepath: str,
    filename: str,
    exposure_time: float,
    timeout_factor: float = 6.0,
):
    SSX_LOGGER.info("Jungfrau - collect dark images")
    # NOTE for now just got what was in old scripts on beamline but reuse the do_manual
    # from jungfrau commissioning
    yield from bps.abs_set(jungfrau.trigger_mode, TriggerMode.SOFTWARE.value, wait=True)

    # TODO Type ignore until new device in use
    SSX_LOGGER.debug("Collect G0")
    dark_acquire_period = exposure_time * DARK_MULTIPLIER["G0"]
    timeout_factor = max(10, timeout_factor * 0.001 / dark_acquire_period)
    yield from bps.abs_set(jungfrau.gain_mode, GainMode.DYNAMIC, wait=True)
    yield from bps.abs_set(jungfrau.file_directory, filepath, wait=True)
    yield from bps.abs_set(jungfrau.file_name, f"{filename}_dark_G0", wait=True)
    yield from do_manual_acquisition(
        jungfrau,  # type: ignore
        exposure_time,
        dark_acquire_period,
        1000,
        timeout_factor,
    )
    yield from bps.sleep(0.3)

    SSX_LOGGER.debug("Collect G1")
    dark_acquire_period = exposure_time * DARK_MULTIPLIER["G1"]
    yield from bps.abs_set(jungfrau.gain_mode, GainMode.FORCESWITCHG1, wait=True)
    yield from bps.abs_set(jungfrau.file_directory, filepath, wait=True)
    yield from bps.abs_set(jungfrau.file_name, f"{filename}_dark_G1", wait=True)
    yield from do_manual_acquisition(
        jungfrau,  # type: ignore
        exposure_time,
        dark_acquire_period,
        1000,
        timeout_factor,
    )
    yield from bps.sleep(0.3)

    SSX_LOGGER.debug("Collect G2")
    yield from bps.abs_set(jungfrau.gain_mode, GainMode.FORCESWITCHG2, wait=True)
    yield from bps.abs_set(jungfrau.file_directory, filepath, wait=True)
    yield from bps.abs_set(jungfrau.file_name, f"{filename}_dark_G2", wait=True)
    yield from do_manual_acquisition(
        jungfrau,  # type: ignore
        exposure_time,
        dark_acquire_period,
        1000,
        timeout_factor,
    )
    yield from bps.sleep(0.3)

    # Put back on dynamic?
    # yield from bps.abs_set(jungfrau.gain_mode, GainMode.dynamic, wait=True)


def setup_jungfrau_for_fixed_target_plan(
    jungfrau: JungFrau1M,
    filepath: str,
    filename: str,
    num_images: int,
    exposure_time: float,
    group: str = "setup_jf_fixed_target",
    wait: bool = True,
):
    SSX_LOGGER.info("Setup JF for fixed-target collection.")
    yield from bps.abs_set(
        jungfrau.trigger_mode, TriggerMode.HARDWARE.value, group=group
    )
    yield from bps.abs_set(jungfrau.gain_mode, GainMode.DYNAMIC, group=group)

    yield from bps.abs_set(jungfrau.file_directory, filepath, group=group)
    yield from bps.abs_set(jungfrau.file_name, filename, group=group)
    yield from bps.abs_set(jungfrau.frame_count, 1, group=group)
    yield from bps.abs_set(jungfrau.trigger_count, num_images, group=group)

    yield from bps.abs_set(jungfrau.exposure_time_s, exposure_time, group=group)
    yield from bps.abs_set(jungfrau.acquire_period_s, exposure_time, group=group)

    SSX_LOGGER.info("Arm Junfgrau")
    yield from bps.abs_set(jungfrau.acquire_start, 1, group=group)

    if wait:
        yield from bps.wait(group=group)
    SSX_LOGGER.debug("JF setup done")


def jungfrau_return_to_normal_plan(jungfrau: JungFrau1M):
    # According to manual, sls_detector_put stop
    yield from bps.abs_set(jungfrau.trigger_count, 1, wait=True)
    yield from bps.abs_set(jungfrau.trigger_mode, TriggerMode.SOFTWARE.value, wait=True)
