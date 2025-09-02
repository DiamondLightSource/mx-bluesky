import asyncio
from functools import partial

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.utils import MsgGenerator
from dodal.common import inject
from ophyd_async.core import WatchableAsyncStatus
from ophyd_async.fastcs.jungfrau import (
    AcquisitionType,
    GainMode,
    Jungfrau,
    create_jungfrau_pedestal_triggering_info,
)
from pydantic import PositiveInt

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils import (
    fly_jungfrau,
    override_file_name_and_path,
)


def do_pedestal_darks(
    exp_time_s: float = 0.001,
    pedestal_frames: PositiveInt = 20,
    pedestal_loops: PositiveInt = 200,
    jungfrau: Jungfrau = inject("jungfrau"),
    path_of_output_file: str | None = None,
    wait: bool = False,
) -> MsgGenerator[WatchableAsyncStatus]:
    """Acquire darks in pedestal mode, using dynamic gain mode. This calibrates the offsets
    for the jungfrau, and must be performed before acquiring real data in dynamic gain mode.

    Args:
        exp_time_s: Length of detector exposure for each frame.
        pedestal_frames: Number of frames acquired per pedestal loop.
        pedestal_loops: Number of times to acquire a set of pedestal_frames
        jungfrau: Jungfrau device
        path_of_output_file: Absolute path of the detector file output, including file name. If None, then use the PathProvider
            set during jungfrau device instantiation
        wait: Optionally block until data collection is complete.
    """

    prev_acq_type = yield from bps.rd(jungfrau.drv.acquisition_type)
    prev_gain = yield from bps.rd(jungfrau.drv.gain_mode)
    prev_pedestal_mode = yield from bps.rd(jungfrau.drv.pedestal_mode)

    if path_of_output_file:
        override_file_name_and_path(jungfrau, path_of_output_file)

    yield from bps.mv(
        jungfrau.drv.acquisition_type,
        AcquisitionType.PEDESTAL,
        jungfrau.drv.gain_mode,
        GainMode.DYNAMIC,
    )

    yield from bps.wait_for([partial(asyncio.sleep, 0.5)])

    trigger_info = create_jungfrau_pedestal_triggering_info(
        exp_time_s, pedestal_frames, pedestal_loops
    )

    # Revert pedestal soft signal, pedestal hard signal, and gain mode to whatever they were before running the plan
    def _revert_acq_type_and_gain():
        yield from bps.mv(
            jungfrau.drv.acquisition_type,
            prev_acq_type,
            jungfrau.drv.gain_mode,
            prev_gain,
            jungfrau.drv.pedestal_mode,
            prev_pedestal_mode,
        )

    @bpp.finalize_decorator(final_plan=lambda: _revert_acq_type_and_gain())
    def _fly_then_revert_acquisition_type_and_gain():
        status = yield from fly_jungfrau(
            jungfrau,
            trigger_info,
            wait,
            log_on_percentage_message="Jungfrau dynamic gain mode darks triggers recieved",
        )
        return status

    return (yield from _fly_then_revert_acquisition_type_and_gain())


def do_darks_full(
    exp_time_s: float = 0.001,
    pedestal_frames: PositiveInt = 20,
    pedestal_loops: PositiveInt = 200,
    jungfrau: Jungfrau = inject("jungfrau"),
    path_of_output_file: str | None = None,
    wait: bool = True,
) -> MsgGenerator[WatchableAsyncStatus]:
    prev_acq_type = yield from bps.rd(jungfrau.drv.acquisition_type)
    prev_gain = yield from bps.rd(jungfrau.drv.gain_mode)
    prev_pedestal_mode = yield from bps.rd(jungfrau.drv.pedestal_mode)

    if path_of_output_file:
        override_file_name_and_path(jungfrau, path_of_output_file)

    trigger_info = create_jungfrau_pedestal_triggering_info(
        exp_time_s, pedestal_frames, pedestal_loops
    )

    yield from bps.mv(
        jungfrau.drv.acquisition_type,
        AcquisitionType.PEDESTAL,
        jungfrau.drv.gain_mode,
        GainMode.DYNAMIC,
    )

    yield from fly_jungfrau(
        jungfrau,
        trigger_info,
        wait,
        log_on_percentage_message=f"Jungfrau {GainMode.DYNAMIC} gain mode darks triggers recieved",
    )
    yield from bps.mv(jungfrau.drv.gain_mode, GainMode.FORCE_SWITCH_G1)
    yield from fly_jungfrau(
        jungfrau,
        trigger_info,
        wait,
        log_on_percentage_message=f"Jungfrau {GainMode.FORCE_SWITCH_G1} gain mode darks triggers recieved",
    )
    yield from bps.mv(jungfrau.drv.gain_mode, GainMode.FORCE_SWITCH_G2)
    yield from fly_jungfrau(
        jungfrau,
        trigger_info,
        wait,
        log_on_percentage_message=f"Jungfrau {GainMode.FORCE_SWITCH_G2} gain mode darks triggers recieved",
    )

    # Revert pedestal soft signal, pedestal hard signal, and gain mode to whatever they were before running the plan
    def _revert_acq_type_and_gain():
        yield from bps.mv(
            jungfrau.drv.acquisition_type,
            prev_acq_type,
            jungfrau.drv.gain_mode,
            prev_gain,
            jungfrau.drv.pedestal_mode,
            prev_pedestal_mode,
        )

    @bpp.finalize_decorator(final_plan=lambda: _revert_acq_type_and_gain())
    def _fly_then_revert_acquisition_type_and_gain():
        status = yield from fly_jungfrau(
            jungfrau,
            trigger_info,
            wait,
            log_on_percentage_message=f"Jungfrau {GainMode.FORCE_SWITCH_G2} gain mode darks triggers recieved",
        )
        return status

    return (yield from _fly_then_revert_acquisition_type_and_gain())
