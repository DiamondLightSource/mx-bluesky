import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from ophyd_async.core import WatchableAsyncStatus
from ophyd_async.fastcs.jungfrau import (
    GainMode,
    create_jungfrau_internal_triggering_info,
    create_jungfrau_pedestal_triggering_info,
)
from pydantic import PositiveInt

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils import (
    fly_jungfrau,
    override_file_path,
)

PEDESTAL_DARKS_RUN = "PEDESTAL DARKS RUN"
STANDARD_DARKS_RUN = "STANDARD DARKS RUN"


def do_pedestal_darks(
    exp_time_s: float = 0.001,
    pedestal_frames: PositiveInt = 20,
    pedestal_loops: PositiveInt = 200,
    jungfrau: CommissioningJungfrau = inject("jungfrau"),
    path_of_output_file: str | None = None,
) -> MsgGenerator[WatchableAsyncStatus]:
    """Acquire darks in pedestal mode, using dynamic gain mode. This calibrates the offsets
    for the jungfrau, and must be performed before acquiring real data in dynamic gain mode.

    When Bluesky triggers the detector in pedestal mode, with pedestal frames F and pedestal loops L,
    the acquisition is managed at the driver level to:
    1. Acquire F-1 frames in dynamic gain mode
    2. Acquire 1 frame in ForceSwitchG1 gain mode
    3. Repeat steps 1-2 L times
    4. Do the first three steps a second time, except use ForceSwitchG2 instead of ForceSwitchG1
    during step 2.

    Args:
        exp_time_s: Length of detector exposure for each frame.
        pedestal_frames: Number of frames acquired per pedestal loop.
        pedestal_loops: Number of times to acquire a set of pedestal_frames
        jungfrau: Jungfrau device
        path_of_output_file: Absolute path of the detector file output, including file name. If None, then use the PathProvider
            set during Jungfrau device instantiation
    """

    @bpp.set_run_key_decorator(PEDESTAL_DARKS_RUN)
    @bpp.run_decorator(md={"subplan_name": PEDESTAL_DARKS_RUN})
    @bpp.finalize_decorator(
        final_plan=lambda: (yield from bps.unstage(jungfrau, wait=True))
    )
    def _do_decorated_plan():
        if path_of_output_file:
            override_file_path(jungfrau, path_of_output_file)

        trigger_info = create_jungfrau_pedestal_triggering_info(
            exp_time_s, pedestal_frames, pedestal_loops
        )
        return (
            yield from fly_jungfrau(
                jungfrau,
                trigger_info,
                trigger_in_pedestal_mode=True,
                wait=True,
                log_on_percentage_prefix="Jungfrau pedestal dynamic gain mode darks triggers recieved",
            )
        )

    return (yield from _do_decorated_plan())


def do_standard_darks(
    gain_mode: GainMode,
    exp_time_s: float = 0.001,
    triggers_per_dark_scan: PositiveInt = 1000,
    jungfrau: CommissioningJungfrau = inject("jungfrau"),
    path_of_output_file: str | None = None,
) -> MsgGenerator:
    """Internally take a set of images at a given gain mode.

    Args:
        gain_mode: Which gain mode to put the Jungfrau into before starting the acquisition.
        exp_time_s: Length of detector exposure for each frame.
        triggers_per_dark_scan: Number of frames acquired for each of the 3 dark scans.
        jungfrau: Jungfrau device
        path_of_output_file: Absolute path of the detector file output, including file name. If None, then use the PathProvider
            set during Jungfrau device instantiation
    """

    @bpp.finalize_decorator(
        final_plan=lambda: (yield from bps.unstage(jungfrau, wait=True))
    )
    @bpp.set_run_key_decorator(STANDARD_DARKS_RUN)
    @bpp.run_decorator(md={"subplan_name": STANDARD_DARKS_RUN})
    def _do_decorated_plan():
        if path_of_output_file:
            override_file_path(jungfrau, path_of_output_file)

        trigger_info = create_jungfrau_internal_triggering_info(
            triggers_per_dark_scan, exp_time_s
        )

        yield from bps.mv(
            jungfrau.drv.gain_mode,
            gain_mode,
        )

        yield from fly_jungfrau(
            jungfrau,
            trigger_info,
            wait=True,
            log_on_percentage_prefix=f"Jungfrau {gain_mode} gain mode darks triggers recieved",
        )

    yield from _do_decorated_plan()
