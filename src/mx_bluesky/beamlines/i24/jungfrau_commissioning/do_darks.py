import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from ophyd_async.core import WatchableAsyncStatus
from ophyd_async.fastcs.jungfrau import (
    AcquisitionType,
    GainMode,
    PedestalMode,
    create_jungfrau_internal_triggering_info,
    create_jungfrau_pedestal_triggering_info,
)
from pydantic import PositiveInt

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils import (
    fly_jungfrau,
)
from mx_bluesky.common.utils.log import LOGGER

STANDARD_DARKS_RUN = "STANDARD DARKS RUN"
PEDESTAL_DARKS_RUN = "PEDESTAL DARKS RUN"


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

    jungfrau._writer._path_info.filename = "pedestal_darks"  # type: ignore

    @bpp.contingency_decorator(
        except_plan=lambda _: (yield from bps.unstage(jungfrau, wait=True))
    )
    @bpp.set_run_key_decorator(PEDESTAL_DARKS_RUN)
    @bpp.run_decorator(md={"subplan_name": PEDESTAL_DARKS_RUN})
    def _do_decorated_plan():
        if path_of_output_file:
            print("Ignoring path overriding for now")
            # override_file_path(jungfrau, path_of_output_file)

        yield from bps.mv(
            jungfrau.drv.acquisition_type,
            AcquisitionType.PEDESTAL,
            jungfrau.drv.gain_mode,
            GainMode.DYNAMIC,
        )

        trigger_info = create_jungfrau_pedestal_triggering_info(
            exp_time_s, pedestal_frames, pedestal_loops
        )
        return (
            yield from fly_jungfrau(
                jungfrau,
                trigger_info,
                wait=True,
                log_on_percentage_prefix="Jungfrau pedestal dynamic gain mode darks triggers recieved",
            )
        )

    return (yield from _do_decorated_plan())


# not used now
def _revert_pedestal_mode(jungfrau: CommissioningJungfrau):
    LOGGER.info("Moving Jungfrau out of pedestal mode...")
    yield from bps.mv(
        jungfrau.drv.acquisition_type,
        AcquisitionType.STANDARD,
        jungfrau.drv.pedestal_mode_state,
        PedestalMode.OFF,
    )


def do_standard_darks(
    gain_mode: GainMode,
    exp_time_s: float = 0.001,
    number_of_triggers: PositiveInt = 1000,
    jungfrau: CommissioningJungfrau = inject("jungfrau"),
):
    jungfrau._writer._path_info.filename = "standard_darks"  # type: ignore  # noqa: SLF001

    @bpp.contingency_decorator(
        except_plan=lambda _: (yield from bps.unstage(jungfrau, wait=True))
    )
    @bpp.set_run_key_decorator(STANDARD_DARKS_RUN)
    @bpp.run_decorator(md={"subplan_name": STANDARD_DARKS_RUN})
    def _do_decorated_plan():
        wait = True
        yield from bps.mv(jungfrau.drv.gain_mode, gain_mode)

        trigger_info = create_jungfrau_internal_triggering_info(
            number_of_triggers, exp_time_s
        )
        yield from fly_jungfrau(
            jungfrau,
            trigger_info,
            wait,
            log_on_percentage_prefix=f"Jungfrau {gain_mode} gain mode darks triggers recieved",
        )

    yield from _do_decorated_plan()


def do_darks_for_dynamic_gain_switching(
    exp_time_s: float = 0.001,
    triggers_per_dark_scan: PositiveInt = 1000,
    jungfrau: CommissioningJungfrau = inject("jungfrau"),
    path_of_output_file: str | None = None,
) -> MsgGenerator:
    """Internally take a set of images at dynamic gain, forced gain 1, and forced gain 2.
        Blocks until all 3 collections are complete.

    Args:
        exp_time_s: Length of detector exposure for each frame.
        triggers_per_dark_scan: Number of frames acquired for each of the 3 dark scans.
        jungfrau: Jungfrau device
        path_of_output_file: Absolute path of the detector file output, including file name. If None, then use the PathProvider
            set during Jungfrau device instantiation
    """

    jungfrau._writer._path_info.filename = "standard_darks"  # type: ignore

    @bpp.contingency_decorator(
        except_plan=lambda _: (yield from bps.unstage(jungfrau, wait=True))
    )
    @bpp.set_run_key_decorator(STANDARD_DARKS_RUN)
    @bpp.run_decorator(md={"subplan_name": STANDARD_DARKS_RUN})
    def _do_decorated_plan():
        wait = True

        if path_of_output_file:
            print("not overriding path using path_of_output_file")
            # override_file_path(jungfrau, path_of_output_file)

        trigger_info = create_jungfrau_internal_triggering_info(
            triggers_per_dark_scan, exp_time_s
        )

        yield from bps.mv(
            jungfrau.drv.gain_mode,
            GainMode.DYNAMIC,
        )

        yield from fly_jungfrau(
            jungfrau,
            trigger_info,
            wait,
            log_on_percentage_prefix=f"Jungfrau {GainMode.DYNAMIC} gain mode darks triggers recieved",
        )
        # yield from bps.mv(jungfrau.drv.gain_mode, GainMode.FORCE_SWITCH_G1)
        # yield from fly_jungfrau(
        #     jungfrau,
        #     trigger_info,
        #     wait,
        #     log_on_percentage_prefix=f"Jungfrau {GainMode.FORCE_SWITCH_G1} gain mode darks triggers recieved",
        # )
        # yield from bps.mv(jungfrau.drv.gain_mode, GainMode.FORCE_SWITCH_G2)
        # yield from fly_jungfrau(
        #     jungfrau,
        #     trigger_info,
        #     wait,
        #     log_on_percentage_prefix=f"Jungfrau {GainMode.FORCE_SWITCH_G2} gain mode darks triggers recieved",
        # )

    yield from _do_decorated_plan()
