import asyncio
import json
from pathlib import PurePath

from bluesky.run_engine import RunEngine
from dodal.beamlines import i24
from dodal.common.beamlines.beamline_utils import (
    BL,
    device_factory,
)
from dodal.devices.i24.commissioning_jungfrau import CommissioningJungfrau
from dodal.utils import BeamlinePrefix, get_beamline_name
from ophyd_async.core import (
    AutoMaxIncrementingPathProvider,
    init_devices,
)

from mx_bluesky.beamlines.i24.jungfrau_commissioning.composites import (
    RotationScanComposite,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils import (
    add_info_logs_to_stdout,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan import (
    multi_rotation_plan_varying_transmission,
)
from mx_bluesky.beamlines.i24.parameters.rotation import (
    MultiRotationScanByTransmissions,
)
from mx_bluesky.common.utils.log import LOGGER, do_default_logging_setup

BL = get_beamline_name("i24")
PREFIX = BeamlinePrefix(BL)

do_default_logging_setup("i24-bluesky.log", 12231)  # Dodal graylog stream
add_info_logs_to_stdout(LOGGER)

with open("rotation_scan_params.json") as f:
    params_json = json.load(f)
params = MultiRotationScanByTransmissions(**params_json)


@device_factory()
def commissioning_jungfrau() -> CommissioningJungfrau:
    return CommissioningJungfrau(
        f"{PREFIX.beamline_prefix}-EA-JFRAU-01:",
        f"{PREFIX.beamline_prefix}-JUNGFRAU-META:FD:",
        AutoMaxIncrementingPathProvider(PurePath(params.storage_directory)),  # type: ignore
    )


async def create_rotation_composite() -> RotationScanComposite:
    with init_devices():
        aperture = i24.aperture()
        attenuator = i24.attenuator()
        jungfrau = commissioning_jungfrau()
        gonio = i24.vgonio()
        synchrotron = i24.synchrotron()
        sample_shutter = i24.sample_shutter()
        zebra = i24.zebra()
        hutch_shutter = i24.shutter()
        beamstop = i24.beamstop()
        det_stage = i24.detector_motion()
        backlight = i24.backlight()
        dcm = i24.dcm()
    return RotationScanComposite(
        aperture,
        attenuator,
        jungfrau,
        gonio,
        synchrotron,
        sample_shutter,
        zebra,
        hutch_shutter,
        beamstop,
        det_stage,
        backlight,
        dcm,
    )


async def do_plan():
    RE = RunEngine()
    devices = await create_rotation_composite()
    RE(
        multi_rotation_plan_varying_transmission(
            devices,
            params,
        )
    )


asyncio.run(do_plan())
