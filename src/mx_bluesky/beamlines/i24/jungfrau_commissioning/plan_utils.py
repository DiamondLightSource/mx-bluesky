from __future__ import annotations

import logging
import sys
from logging import Logger
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
from ophyd_async.fastcs.jungfrau import (
    AcquisitionType,
    GainMode,
)

from mx_bluesky.beamlines.i24.jungfrau_commissioning.callbacks.metadata_writer import (
    JsonMetadataWriter,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.utility_plans import (
    read_devices_for_metadata,
)
from mx_bluesky.beamlines.i24.parameters.constants import (
    PlanNameConstants as I24PlanNameConstants,
)
from mx_bluesky.common.utils.log import LOGGER

JF_COMPLETE_GROUP = "JF complete"


def fly_jungfrau(
    jungfrau: CommissioningJungfrau,
    trigger_info: TriggerInfo,
    wait: bool = False,
    log_on_percentage_prefix="Jungfrau data collection triggers recieved",
    pedestals=False,
    do_read=False,
    params=None,  # set this if do read is true
    composite=None,  # set this if do read is true
) -> MsgGenerator[WatchableAsyncStatus]:
    """Stage, prepare, and kickoff Jungfrau with a configured TriggerInfo. Optionally wait
    for completion.

    Note that this plan doesn't include unstaging of the Jungfrau, and a run must be open
    before this plan is called.

    Args:
    jungfrau: Jungfrau device.
    trigger_info: TriggerInfo which should be acquired using jungfrau util functions create_jungfrau_internal_triggering_info.
        or create_jungfrau_external_triggering_info.
    wait: Optionally block until data collection is complete.
    log_on_percentage_prefix: String that will be appended to the "percentage completion" logging message.
    """

    @bpp.contingency_decorator(
        except_plan=lambda _: (yield from bps.unstage(jungfrau, wait=True))
    )
    def _fly_with_unstage_contingency():
        yield from bps.stage(jungfrau, wait=True)
        LOGGER.info("Setting up detector...")
        if pedestals:
            LOGGER.info("Putting detector into pedestal mode...")
            yield from bps.mv(
                jungfrau.drv.acquisition_type,
                AcquisitionType.PEDESTAL,
                jungfrau.drv.gain_mode,
                GainMode.DYNAMIC,
            )
        yield from bps.prepare(jungfrau, trigger_info, wait=True)

        # horrible hack to put metadata file at right place - needs to happen after prepare since that's when path provider works out its path
        if do_read:
            metadata_writer = JsonMetadataWriter(jungfrau._writer)

            @bpp.subs_decorator([metadata_writer])
            @bpp.set_run_key_decorator(I24PlanNameConstants.ROTATION_META_READ)
            @bpp.run_decorator(
                md={
                    "subplan_name": I24PlanNameConstants.ROTATION_META_READ,
                    "scan_points": [params.scan_points],
                    "rotation_scan_params": params.model_dump_json(),
                }
            )
            # Write metadata json file
            def _do_read():
                yield from read_devices_for_metadata(composite)

            yield from _do_read()

        LOGGER.info("Detector prepared. Starting acquisition")
        LOGGER.info("doing a 1s sleep before kickoff")
        yield from bps.sleep(1)
        yield from bps.kickoff(jungfrau, wait=True)

        yield from bps.create("FILENAME")
        yield from bps.read(jungfrau._writer.file_path)
        yield from bps.read(jungfrau._writer.file_name)
        yield from bps.save()

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


def add_info_logs_to_stdout(logger: Logger):
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    stdout_handler.setFormatter(formatter)

    logger.addHandler(stdout_handler)
