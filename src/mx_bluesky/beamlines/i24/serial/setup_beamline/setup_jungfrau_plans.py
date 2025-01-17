import bluesky.plan_stubs as bps
from dodal.devices.i24.jungfrau import GainMode, JungFrau1M, TriggerMode

from mx_bluesky.beamlines.i24.serial.log import SSX_LOGGER

# TODO check the zebra plans


def setup_and_run_jungfrau_for_darks_plan(jungfrau: JungFrau1M):
    # There's alread a plan for this in jf_commissioning.
    # See
    pass


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
    yield from bps.abs_set(jungfrau.trigger_mode, TriggerMode.HARDWARE, group=group)
    yield from bps.abs_set(jungfrau.gain_mode, GainMode.dynamic, group=group)

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
    yield from bps.abs_set(jungfrau.trigger_mode, TriggerMode.SOFTWARE, wait=True)
