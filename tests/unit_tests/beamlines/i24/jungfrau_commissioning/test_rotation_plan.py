from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import bluesky.plan_stubs as bps
from bluesky.run_engine import RunEngine
from dodal.devices.i24.vgonio import VerticalGoniometer
from dodal.devices.zebra.zebra import RotationDirection, Zebra

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans import (
    JfDevices,
    cleanup_plan,
    get_rotation_scan_plan,
    move_to_start_w_buffer,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.params import (
    RotationScanParameters,
)
from mx_bluesky.beamlines.i24.serial.setup_beamline.setup_zebra_plans import arm_zebra


def _fake_wait_for_writing(*_, **__):
    yield from bps.sleep(0.2)


@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans.wait_for_writing",
    _fake_wait_for_writing,
)
@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans.JsonMetadataWriter",
)
def test_rotation_scan_get_plan(
    json_callback: MagicMock,
    fake_create_devices_function: Callable[..., JfDevices],
    params: RotationScanParameters,
    tmp_path: Path,
):
    params.storage_directory = str(tmp_path)
    with patch(
        "mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans.create_rotation_scan_devices",
        fake_create_devices_function,
    ):
        plan = get_rotation_scan_plan(params)
    assert plan is not None


@patch(
    "bluesky.plan_stubs.wait",
)
async def test_cleanup_plan(bps_wait, fake_devices: JfDevices, RE: RunEngine):
    zebra: Zebra = fake_devices["zebra"]
    RE(arm_zebra(zebra))
    assert (await zebra.pc.arm.armed.get_value()).value == 1  # type: ignore
    RE(cleanup_plan(zebra))
    assert (await zebra.pc.arm.armed.get_value()).value == 0  # type: ignore


@patch(
    "bluesky.plan_stubs.wait",
)
@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans.JsonMetadataWriter",
)
async def test_move_to_start(
    nexus_callback: MagicMock,
    bps_wait: MagicMock,
    fake_devices: JfDevices,
    RE: RunEngine,
    params: RotationScanParameters,
):
    gonio: VerticalGoniometer = fake_devices["gonio"]
    RE(
        move_to_start_w_buffer(
            gonio.omega,
            params.omega_start_deg,
            wait=True,
            offset=2,
            direction=RotationDirection.POSITIVE,
        )
    )
    assert await gonio.omega.user_readback.get_value() == -2


@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans.wait_for_writing",
    _fake_wait_for_writing,
)
@patch(
    "bluesky.plan_stubs.wait",
)
@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans.JsonMetadataWriter",
)
async def test_rotation_scan_do_plan(
    nexus_callback: MagicMock,
    bps_wait: MagicMock,
    fake_create_devices_function: Callable[..., JfDevices],
    RE: RunEngine,
    params: RotationScanParameters,
):
    with patch(
        "mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans.create_rotation_scan_devices",
        fake_create_devices_function,
    ):
        plan = get_rotation_scan_plan(params)

    RE(plan)
    devices = fake_create_devices_function()
    gonio: VerticalGoniometer = devices["gonio"]
    assert await gonio.omega.user_readback.get_value() == -367.6
