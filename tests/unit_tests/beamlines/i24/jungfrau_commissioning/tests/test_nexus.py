import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from bluesky.run_engine import RunEngine
from dodal.devices.zebra import RotationDirection

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans import (
    get_rotation_scan_plan,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.params import (
    RotationScanParameters,
)


@patch(
    "bluesky.plan_stubs.wait",
)
@patch(
    "jungfrau_commissioning.plans.rotation_scan_plans.NexusFileHandlerCallback",
)
def test_rotation_scan_plan_nexus_callback(
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

    callback_instance: MagicMock = nexus_callback.return_value
    callback_calls = callback_instance.call_args_list
    assert len(callback_calls) == 8
    call_1 = callback_calls[0]
    assert call_1.args[0] == "start"
    assert call_1.args[1]["subplan_name"] == "rotation_scan_with_cleanup"
    assert "rotation_scan_params" in call_1.args[1]
    assert "position" in call_1.args[1]
    assert "beam_params" in call_1.args[1]


@patch(
    "bluesky.plan_stubs.wait",
)
@patch(
    "jungfrau_commissioning.callbacks.nexus_writer.JFRotationNexusWriter",
)
def test_rotation_scan_plan_nexus_callback_gets_readings(
    nexus_writer: MagicMock,
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
    nexus_writer.assert_called_with(
        RotationScanParameters(
            rotation_axis="omega",
            scan_width_deg=360.0,
            image_width_deg=0.1,
            omega_start_deg=0.0,
            exposure_time_s=0.001,
            acquire_time_s=0.001,
            x=0,
            y=0,
            z=0,
            rotation_direction=RotationDirection.POSITIVE,
            offset_deg=1.0,
            shutter_opening_time_s=0.6,
            storage_directory="/tmp/jungfrau_data/",
            nexus_filename="scan",
        ),
        0.65,
        9999999,
        0.1,
    )


@patch(
    "bluesky.plan_stubs.wait",
)
def test_rotation_scan_plan_nexus_callback_writes_files(
    bps_wait: MagicMock,
    fake_create_devices_function,
    RE: RunEngine,
):
    minimal_params = RotationScanParameters.from_file("example_params.json")
    nexus_filename = str(
        Path(minimal_params.storage_directory)
        / (minimal_params.nexus_filename + ".nxs")
    )
    master_filename = str(
        Path(minimal_params.storage_directory)
        / (minimal_params.nexus_filename + "_master.h5")
    )

    if os.path.isfile(nexus_filename):
        os.remove(nexus_filename)
    if os.path.isfile(master_filename):
        os.remove(master_filename)

    with patch(
        "jungfrau_commissioning.plans.rotation_scan_plans.create_rotation_scan_devices",
        fake_create_devices_function,
    ):
        plan = get_rotation_scan_plan(minimal_params)

    RE(plan)

    assert os.path.isfile(nexus_filename)
    assert os.path.isfile(master_filename)
    os.remove(nexus_filename)
    os.remove(master_filename)
