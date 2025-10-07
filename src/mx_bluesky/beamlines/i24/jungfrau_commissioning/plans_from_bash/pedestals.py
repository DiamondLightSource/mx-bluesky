import asyncio

from bluesky.run_engine import RunEngine
from dodal.beamlines import i24
from ophyd_async.core import init_devices

from mx_bluesky.beamlines.i24.jungfrau_commissioning.do_darks import do_pedestal_darks
from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils import (
    add_info_logs_to_stdout,
)
from mx_bluesky.common.utils.log import LOGGER, do_default_logging_setup

do_default_logging_setup("i24-bluesky.log", 12231)  # Dodal graylog stream
add_info_logs_to_stdout(LOGGER)
import json
from pathlib import PurePath

from dodal.common.beamlines.beamline_utils import (
    BL,
    device_factory,
)
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from dodal.utils import BeamlinePrefix, get_beamline_name
from ophyd_async.core import (
    AutoMaxIncrementingPathProvider,
)
from pydantic import BaseModel

BL = get_beamline_name("i24")
PREFIX = BeamlinePrefix(BL)


class PedestalParams(BaseModel):
    exp_time_s: float
    pedestal_frames: int
    pedestal_loops: int
    storage_directory: str


# get params
with open("pedestal_scan_params.json") as f:
    params_json = json.load(f)
params = PedestalParams(**params_json)


@device_factory()
def commissioning_jungfrau() -> CommissioningJungfrau:
    return CommissioningJungfrau(
        f"{PREFIX.beamline_prefix}-EA-JFRAU-01:",
        f"{PREFIX.beamline_prefix}-JUNGFRAU-META:FD:",
        AutoMaxIncrementingPathProvider(PurePath(params.storage_directory)),  # type: ignore
    )


async def do_plan():
    RE = RunEngine()
    with init_devices():
        jf = i24.commissioning_jungfrau()
    RE(
        do_pedestal_darks(
            params.exp_time_s, params.pedestal_frames, params.pedestal_loops, jf
        )
    )


asyncio.run(do_plan())
