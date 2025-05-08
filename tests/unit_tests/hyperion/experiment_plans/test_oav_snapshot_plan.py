from collections.abc import Generator
from datetime import datetime
from unittest.mock import patch

import pydantic
import pytest
from bluesky.simulators import RunEngineSimulator, assert_message_and_return_remaining
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.areadetector.plugins.CAM import ColorMode
from dodal.devices.backlight import Backlight
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.smargon import Smargon

from mx_bluesky.common.parameters.components import WithSnapshot
from mx_bluesky.common.parameters.constants import DocDescriptorNames
from mx_bluesky.hyperion.experiment_plans.oav_snapshot_plan import (
    OAV_SNAPSHOT_SETUP_SHOT,
    OavSnapshotComposite,
    oav_snapshot_plan,
)

from ....conftest import raw_params_from_file


@pytest.fixture
def oav_snapshot_params():
    return WithSnapshot(
        **raw_params_from_file(
            "tests/test_data/parameter_json_files/test_oav_snapshot_params.json"
        )
    )


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class CompositeImpl(OavSnapshotComposite):
    smargon: Smargon
    oav: OAV
    aperture_scatterguard: ApertureScatterguard
    backlight: Backlight


@pytest.fixture
def oav_snapshot_composite(smargon, oav, aperture_scatterguard, backlight):
    return CompositeImpl(
        smargon=smargon,
        oav=oav,
        aperture_scatterguard=aperture_scatterguard,
        backlight=backlight,
    )


@pytest.fixture(autouse=True)
def fixed_datetime() -> Generator[str, None, None]:
    with patch(
        "mx_bluesky.hyperion.experiment_plans.oav_snapshot_plan.datetime", spec=datetime
    ) as mock_datetime:
        mock_datetime.now.return_value = datetime.fromisoformat(
            "2024-06-07T10:06:23.12"
        )
        yield "10062312"


def test_oav_snapshot_plan_issues_rotations_and_generates_events(
    fixed_datetime, oav_snapshot_params, oav_snapshot_composite, sim_run_engine
):
    msgs = sim_run_engine.simulate_plan(
        oav_snapshot_plan(
            oav_snapshot_composite,
            oav_snapshot_params,
            OAVParameters(oav_config_json="tests/test_data/test_OAVCentring.json"),
        )
    )

    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "oav-cam-color_mode"
        and msg.args[0] == ColorMode.RGB1,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "oav-cam-acquire_period"
        and msg.args[0] == 0.05,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "oav-cam-acquire_time"
        and msg.args[0] == 0.075,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "oav-cam-gain"
        and msg.args[0] == 1,
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "oav-zoom_controller"
        and msg.args[0] == "5.0x",
    )
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: msg.command == "set"
        and msg.obj.name == "oav-snapshot-directory"
        and msg.args[0] == "/tmp/my_snapshots",
    )
    for expected in [
        {"omega": 0, "filename": "10062312_oav_snapshot_0"},
        {"omega": 90, "filename": "10062312_oav_snapshot_90"},
        {"omega": 180, "filename": "10062312_oav_snapshot_180"},
        {"omega": 270, "filename": "10062312_oav_snapshot_270"},
    ]:
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "set"
            and msg.obj.name == "smargon-omega"
            and msg.args[0] == expected["omega"]
            and msg.kwargs["group"] == OAV_SNAPSHOT_SETUP_SHOT,
        )
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "set"
            and msg.obj.name == "oav-snapshot-filename"
            and msg.args[0] == expected["filename"],
        )
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "trigger"
            and msg.obj.name == "oav-snapshot"
            and msg.kwargs["group"] is None,
        )
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "wait" and msg.kwargs["group"] is None,
        )
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "create"
            and msg.kwargs["name"]
            == DocDescriptorNames.OAV_ROTATION_SNAPSHOT_TRIGGERED,
        )
        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "read" and msg.obj.name == "oav"
        )
        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "save"
        )


def test_oav_snapshot_plan_generates_snapshots_events_without_triggering_oav_when_using_grid_snapshots(
    fixed_datetime,
    oav_snapshot_params: WithSnapshot,
    oav_snapshot_composite: CompositeImpl,
    oav_parameters_for_rotation: OAVParameters,
    sim_run_engine: RunEngineSimulator,
):
    oav_snapshot_params.use_grid_snapshots = True
    oav_snapshot_params.snapshot_omegas_deg = [0, 90]

    msgs = sim_run_engine.simulate_plan(
        oav_snapshot_plan(
            oav_snapshot_composite, oav_snapshot_params, oav_parameters_for_rotation
        )
    )

    assert not [
        msg
        for msg in msgs
        if msg.command == "trigger" and msg.obj is oav_snapshot_composite.oav
    ]
    assert not [
        msg
        for msg in msgs
        if msg.command == "set" and msg.obj is oav_snapshot_composite.smargon.omega
    ]
    expected_snapshot_directory = str(oav_snapshot_params.snapshot_directory)
    msgs = assert_message_and_return_remaining(
        msgs,
        lambda msg: (
            msg.command == "set"
            and msg.obj is oav_snapshot_composite.oav.snapshot.directory
            and msg.args[0] == expected_snapshot_directory
        ),
    )
    for _ in 0, 90:
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "create"
            and msg.kwargs["name"]
            == DocDescriptorNames.OAV_ROTATION_SNAPSHOT_TRIGGERED,
        )
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "read" and msg.obj is oav_snapshot_composite.oav,
        )
        msgs = assert_message_and_return_remaining(
            msgs,
            lambda msg: msg.command == "read"
            and msg.obj is oav_snapshot_composite.smargon,
        )
        msgs = assert_message_and_return_remaining(
            msgs, lambda msg: msg.command == "save"
        )
