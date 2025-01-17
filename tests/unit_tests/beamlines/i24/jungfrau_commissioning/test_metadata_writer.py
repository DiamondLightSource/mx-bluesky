import os
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import bluesky.plan_stubs as bps
from bluesky.run_engine import RunEngine

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans import (
    JfDevices,
    get_rotation_scan_plan,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.params import (
    EXPERIMENT_PARAM_DUMP_FILENAME,
    READING_DUMP_FILENAME,
    RotationScanParameters,
)


def _fake_wait_for_writing(*_, **__):
    yield from bps.sleep(0.2)


@patch(
    "bluesky.plan_stubs.wait",
)
@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans.JsonMetadataWriter",
)
@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans.wait_for_writing",
    _fake_wait_for_writing,
)
def test_rotation_scan_plan_metadata_callback_setup(
    json_callback: MagicMock,
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

    callback_instance: MagicMock = json_callback.return_value
    callback_calls = callback_instance.call_args_list
    assert len(callback_calls) == 8
    call_1 = callback_calls[0]
    assert call_1.args[0] == "start"
    assert call_1.args[1]["subplan_name"] == "rotation_scan_with_cleanup"
    assert "rotation_scan_params" in call_1.args[1]


@patch(
    "bluesky.plan_stubs.wait",
)
@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans.JsonMetadataWriter",
)
@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans.wait_for_writing",
    _fake_wait_for_writing,
)
def test_rotation_scan_plan_metadata_callback_calls(
    json_callback: MagicMock,
    bps_wait: MagicMock,
    fake_create_devices_function: Callable[..., JfDevices],
    RE: RunEngine,
    params: RotationScanParameters,
):
    with patch(
        "mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans.create_rotation_scan_devices",
        fake_create_devices_function,
    ):
        devices = fake_create_devices_function()
        devices["gonio"].x.user_readback.sim_put(0.1)  # type: ignore
        devices["gonio"].yh.user_readback.sim_put(0.2)  # type: ignore
        devices["gonio"].z.user_readback.sim_put(0.3)  # type: ignore
        plan = get_rotation_scan_plan(params)

    RE(plan)

    callback_instance: MagicMock = json_callback.return_value
    callback_calls = callback_instance.call_args_list
    pos_event_data = callback_calls[3][0][1]["data"]
    assert pos_event_data["vgonio_x"] == 0.1
    assert pos_event_data["vgonio_yh"] == 0.2
    assert pos_event_data["vgonio_z"] == 0.3
    beam_event_data = callback_calls[5][0][1]["data"]
    for key in (
        "beam_params_transmission",
        "beam_params_wavelength",
        "beam_params_energy",
        "beam_params_intensity",
        "beam_params_flux_xbpm2",
        "beam_params_flux_xbpm3",
    ):
        assert key in beam_event_data.keys()


@patch(
    "bluesky.plan_stubs.wait",
)
@patch(
    "mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans.wait_for_writing",
    _fake_wait_for_writing,
)
def test_rotation_scan_plan_metadata_callback_writes_files(
    bps_wait: MagicMock,
    fake_create_devices_function: Callable[..., JfDevices],
    RE: RunEngine,
    params: RotationScanParameters,
    tmp_path: Path,
):
    with open(tmp_path / "run_number.txt", "w") as f:
        f.write("00005")
    params.storage_directory = str(tmp_path)
    params.data_filename = "test"
    tm = fake_create_devices_function()["beam_params"].transmission.get()
    expt_dir = f"{6:05d}_{params.data_filename}_scan_{int(params.scan_width_deg)}deg_{tm:.3f}transmission"
    params_file_path = (
        Path(params.storage_directory) / expt_dir
    ) / EXPERIMENT_PARAM_DUMP_FILENAME
    reading_file_path = (
        Path(params.storage_directory) / expt_dir
    ) / READING_DUMP_FILENAME

    if os.path.isfile(params_file_path):
        os.remove(params_file_path)
    if os.path.isfile(reading_file_path):
        os.remove(reading_file_path)

    with patch(
        "mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans.create_rotation_scan_devices",
        fake_create_devices_function,
    ):
        plan = get_rotation_scan_plan(params)

    RE(plan)

    assert os.path.isfile(params_file_path)
    assert os.path.isfile(reading_file_path)
    os.remove(params_file_path)
    os.remove(reading_file_path)
