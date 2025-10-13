from pathlib import PurePath
from typing import cast

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.utils import MsgGenerator
from dodal.common.watcher_utils import log_on_percentage_complete
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from ophyd_async.core import (
    AutoIncrementingPathProvider,
    StaticFilenameProvider,
    TriggerInfo,
    WatchableAsyncStatus,
)
from ophyd_async.fastcs.jungfrau import AcquisitionType, GainMode

from mx_bluesky.common.utils.log import LOGGER

JF_COMPLETE_GROUP = "JF complete"


def fly_jungfrau(
    jungfrau: CommissioningJungfrau,
    trigger_info: TriggerInfo,
    trigger_in_pedestal_mode=False,
    wait: bool = False,
    log_on_percentage_prefix="Jungfrau data collection triggers recieved",
) -> MsgGenerator[WatchableAsyncStatus]:
    """Stage, prepare, and kickoff Jungfrau with a configured TriggerInfo. Optionally wait
    for completion.

    Note that this plan doesn't include unstaging of the Jungfrau, and a run must be open
    before this plan is called.

    Args:
    jungfrau: Jungfrau device.
    trigger_info: TriggerInfo which should be acquired using jungfrau util functions.
    trigger_in_pedestal_mode: Must set to true if attempting to trigger in pedestal mode.
    wait: Optionally block until data collection is complete.
    log_on_percentage_prefix: String that will be appended to the "percentage completion" logging message.
    """

    @bpp.contingency_decorator(
        except_plan=lambda _: (yield from bps.unstage(jungfrau, wait=True))
    )
    def _fly_with_unstage_contingency():
        LOGGER.info("Staging detector...")
        yield from bps.stage(jungfrau, wait=True)
        if trigger_in_pedestal_mode:
            LOGGER.info("Jungfrau will be triggered in pedestal mode")
            yield from bps.mv(
                jungfrau.drv.acquisition_type,
                AcquisitionType.PEDESTAL,
                jungfrau.drv.gain_mode,
                GainMode.DYNAMIC,
            )
        LOGGER.info("Preparing detector...")
        yield from bps.prepare(jungfrau, trigger_info, wait=True)
        LOGGER.info("Detector prepared. Starting acquisition")
        yield from bps.kickoff(jungfrau, wait=True)
        LOGGER.info("Waiting for acquisition to complete...")
        status = yield from bps.complete(jungfrau, group=JF_COMPLETE_GROUP)

        # StandardDetector.complete converts regular status to watchable status,
        # but bluesky plan stubs can't see this currently
        status = cast(WatchableAsyncStatus, status)
        log_on_percentage_complete(status, log_on_percentage_prefix, 10)
        if wait:
            yield from bps.wait(JF_COMPLETE_GROUP)
        return status

    return (yield from _fly_with_unstage_contingency())


def override_file_path(jungfrau: CommissioningJungfrau, path_of_output_file: str):
    """While we should generally use device instantiation to set the path,
    during commissioning, it is useful to be able to explicitly set the filename
    and path.

    This function must be called before the Jungfrau is prepared.
    """
    _file_path = PurePath(path_of_output_file)
    _new_filename_provider = StaticFilenameProvider(_file_path.name)
    jungfrau._writer._path_info = AutoIncrementingPathProvider(  # noqa: SLF001
        _new_filename_provider, _file_path.parent
    )
