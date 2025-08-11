from typing import cast

import bluesky.plan_stubs as bps
from dodal.common import inject
from ophyd_async.core import WatchableAsyncStatus, Watcher
from ophyd_async.fastcs.jungfrau import (
    Jungfrau,
    create_jungfrau_external_triggering_info,
)

from mx_bluesky.common.utils.log import LOGGER


class LogOnPercentageProgressWatcher(Watcher[int]):
    def __init__(
        self,
        status: WatchableAsyncStatus[int],
        message_prefix: str,
        percent_interval: int = 25,
    ):
        status.watch(self)
        self.percent_interval = percent_interval
        self.current_percent_interval = 0
        self.message_prefix = message_prefix

    def __call__(
        self,
        current: int | None = None,
        initial: int | None = None,
        target: int | None = None,
        name: str | None = None,
        unit: str | None = None,
        precision: int | None = None,
        fraction: float | None = None,
        time_elapsed: float | None = None,
        time_remaining: float | None = None,
    ):
        if isinstance(current, int) and isinstance(target, int) and target:
            current_percent = int((current / target) * 100)
            if (
                current_percent
                >= (self.current_percent_interval + 1) * self.percent_interval
            ):
                LOGGER.info(f"{self.message_prefix}: {current_percent}%")
                self.current_percent_interval = current_percent // self.percent_interval


def log_on_percentage_complete(
    status: WatchableAsyncStatus[int], message_prefix: str, percent_interval: int = 25
):
    LogOnPercentageProgressWatcher(status, message_prefix, percent_interval)


# TODO: make the pathprovider adjustable with a absolute path to file param
def do_manual_acquisition(
    exp_time_s: float,
    period_between_frames_s: float,
    frames_per_trigger: int = 1,
    total_triggers: int = 1,
    jungfrau: Jungfrau = inject("jungfrau"),
    wait: bool = False,
):
    trigger_info = create_jungfrau_external_triggering_info(
        total_triggers, frames_per_trigger, exp_time_s, period_between_frames_s
    )
    yield from bps.stage(jungfrau)
    LOGGER.info("Setting up detector...")
    yield from bps.prepare(jungfrau, trigger_info, wait=True)
    LOGGER.info("Detector prepared. Starting acquisition")

    yield from bps.kickoff(jungfrau, wait=True)

    LOGGER.info("Waiting for acquisition to complete...")
    status = yield from bps.complete(jungfrau, group="jf_complete")

    # StandardDetector.complete converts regular status to watchable status,
    # but bluesky plan stubs can't see this currently
    status = cast(WatchableAsyncStatus, status)
    log_on_percentage_complete(status, "Jungfrau data collection triggers recieved", 10)
    if wait:
        yield from bps.wait("jf_complete")
    return status
