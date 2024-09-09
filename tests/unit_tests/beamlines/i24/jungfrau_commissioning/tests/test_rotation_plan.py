from unittest.mock import MagicMock, patch

from bluesky.run_engine import RunEngine
from dodal.devices.i24.vgonio import VGonio
from dodal.devices.zebra import RotationDirection, Zebra

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans import (
    cleanup_plan,
    get_rotation_scan_plan,
    move_to_start_w_buffer,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.zebra_plans import arm_zebra
from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.params import (
    RotationScanParameters,
)


@patch(
    "jungfrau_commissioning.plans.rotation_scan_plans.NexusFileHandlerCallback",
)
def test_rotation_scan_get_plan(
    nexus_callback: MagicMock, fake_create_devices_function
):
    minimal_params = RotationScanParameters.from_file("example_params.json")
    with patch(
        "jungfrau_commissioning.plans.rotation_scan_plans.create_rotation_scan_devices",
        fake_create_devices_function,
    ):
        plan = get_rotation_scan_plan(minimal_params)
    assert plan is not None
    nexus_callback.assert_called_once()


@patch(
    "bluesky.plan_stubs.wait",
)
def test_cleanup_plan(bps_wait, fake_devices, RE: RunEngine):
    zebra: Zebra = fake_devices["zebra"]
    RE(arm_zebra(zebra))
    assert zebra.pc.armed.get() == 1
    RE(cleanup_plan(zebra))
    assert zebra.pc.armed.get() == 0


@patch(
    "bluesky.plan_stubs.wait",
)
@patch(
    "jungfrau_commissioning.plans.rotation_scan_plans.NexusFileHandlerCallback",
)
def test_move_to_start(
    nexus_callback: MagicMock, bps_wait: MagicMock, fake_devices, RE: RunEngine
):
    params = RotationScanParameters.from_file("example_params.json")
    gonio: VGonio = fake_devices["gonio"]
    RE(
        move_to_start_w_buffer(
            gonio.omega,
            params.omega_start_deg,
            wait=True,
            offset=2,
            direction=RotationDirection.POSITIVE,
        )
    )
    assert gonio.omega.user_readback.get() == -2


@patch(
    "bluesky.plan_stubs.wait",
)
@patch(
    "jungfrau_commissioning.plans.rotation_scan_plans.NexusFileHandlerCallback",
)
def test_rotation_scan_do_plan(
    nexus_callback: MagicMock,
    bps_wait: MagicMock,
    fake_create_devices_function,
    RE: RunEngine,
):
    minimal_params = RotationScanParameters.from_file("example_params.json")
    with patch(
        "jungfrau_commissioning.plans.rotation_scan_plans.create_rotation_scan_devices",
        fake_create_devices_function,
    ):
        plan = get_rotation_scan_plan(minimal_params)

    RE(plan)
    devices = fake_create_devices_function()
    gonio: VGonio = devices["gonio"]
    assert gonio.omega.user_readback.get() == -360.5
