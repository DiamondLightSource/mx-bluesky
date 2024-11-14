from unittest.mock import MagicMock, patch

import pytest
from bluesky.run_engine import RunEngine
from event_model import RunStart

from mx_bluesky.common.parameters.components import IspybExperimentType
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import rotation_scan
from mx_bluesky.hyperion.external_interaction.callbacks.common.callback_util import (
    create_rotation_callbacks,
)
from mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback import (
    RotationISPyBCallback,
)
from mx_bluesky.hyperion.external_interaction.callbacks.rotation.nexus_callback import (
    RotationNexusFileCallback,
)
from mx_bluesky.hyperion.external_interaction.exceptions import ISPyBDepositionNotMade
from mx_bluesky.hyperion.external_interaction.ispyb.data_model import (
    ScanDataInfo,
)
from mx_bluesky.hyperion.external_interaction.ispyb.ispyb_store import (
    IspybIds,
    StoreInIspyb,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.rotation import RotationScan

from .....conftest import raw_params_from_file


@pytest.fixture
def params():
    return RotationScan(
        **raw_params_from_file(
            "tests/test_data/parameter_json_files/good_test_rotation_scan_parameters.json"
        )
    )


def activate_callbacks(cbs: tuple[RotationNexusFileCallback, RotationISPyBCallback]):
    cbs[1].active = True
    cbs[0].active = True


@pytest.fixture
def do_rotation_scan(
    params: RotationScan, fake_create_rotation_devices, oav_parameters_for_rotation
):
    return rotation_scan(
        fake_create_rotation_devices, params, oav_parameters_for_rotation
    )


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.rotation.nexus_callback.NexusWriter",
    autospec=True,
)
def test_nexus_handler_gets_documents_in_plan(
    nexus_writer: MagicMock,
    do_rotation_scan,
    RE: RunEngine,
):
    nexus_writer.return_value.data_filename = "test_full_filename"
    nexus_callback, _ = create_rotation_callbacks()
    activate_callbacks((nexus_callback, _))
    nexus_callback.activity_gated_start = MagicMock(
        side_effect=nexus_callback.activity_gated_start
    )
    RE.subscribe(nexus_callback)
    RE(do_rotation_scan)

    subplans = []
    for call in nexus_callback.activity_gated_start.call_args_list:  #  type: ignore
        subplans.append(call.args[0].get("subplan_name"))

    assert CONST.PLAN.ROTATION_OUTER in subplans


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.rotation.nexus_callback.NexusWriter",
    autospec=True,
)
def test_nexus_handler_only_writes_once(
    nexus_writer: MagicMock, RE: RunEngine, do_rotation_scan
):
    nexus_writer.return_value.data_filename = "test_full_filename"
    cb = RotationNexusFileCallback()
    cb.active = True
    RE.subscribe(cb)
    RE(do_rotation_scan)
    nexus_writer.assert_called_once()
    assert cb.writer is not None
    cb.writer.create_nexus_file.assert_called_once()  # type: ignore


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.rotation.nexus_callback.NexusWriter",
    autospec=True,
)
@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.zocalo_callback.ZocaloTrigger",
    autospec=True,
)
@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback.StoreInIspyb",
    autospec=True,
)
def test_zocalo_start_and_end_not_triggered_if_ispyb_ids_not_present(
    ispyb_store,
    zocalo_trigger_class,
    nexus_writer,
    RE: RunEngine,
    params: RotationScan,
    do_rotation_scan,
):
    nexus_writer.return_value.data_filename = "test_full_filename"
    nexus_callback, ispyb_callback = create_rotation_callbacks()
    activate_callbacks((nexus_callback, ispyb_callback))
    zocalo_trigger = zocalo_trigger_class.return_value

    ispyb_callback.ispyb = MagicMock(spec=StoreInIspyb)
    ispyb_callback.params = params
    with pytest.raises(ISPyBDepositionNotMade):
        RE.subscribe(nexus_callback)
        RE.subscribe(ispyb_callback)
        RE(do_rotation_scan)
    zocalo_trigger.run_start.assert_not_called()  # type: ignore


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.rotation.nexus_callback.NexusWriter",
    autospec=True,
)
@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.zocalo_callback.ZocaloTrigger",
    autospec=True,
)
@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback.StoreInIspyb"
)
def test_ispyb_triggered_before_zocalo(
    ispyb_store, zocalo_trigger_class, nexus_writer, RE: RunEngine, do_rotation_scan
):
    mock_store_in_ispyb_instance = MagicMock(spec=StoreInIspyb)
    returned_ids = IspybIds(data_collection_group_id=0, data_collection_ids=(0,))
    mock_store_in_ispyb_instance.begin_deposition.return_value = returned_ids
    mock_store_in_ispyb_instance.update_deposition.return_value = returned_ids

    ispyb_store.return_value = mock_store_in_ispyb_instance
    nexus_writer.return_value.data_filename = "test_full_filename"
    nexus_callback, ispyb_callback = create_rotation_callbacks()
    activate_callbacks((nexus_callback, ispyb_callback))
    ispyb_callback.emit_cb.stop = MagicMock()  # type: ignore

    parent_mock = MagicMock()
    parent_mock.attach_mock(zocalo_trigger_class.return_value, "zocalo")
    parent_mock.attach_mock(mock_store_in_ispyb_instance, "ispyb")

    RE.subscribe(nexus_callback)
    RE.subscribe(ispyb_callback)
    RE(do_rotation_scan)

    call_names = [call[0] for call in parent_mock.method_calls]

    assert "ispyb.begin_deposition" in call_names
    assert "zocalo.run_start" in call_names

    assert call_names.index("ispyb.begin_deposition") < call_names.index(
        "zocalo.run_start"
    )


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.zocalo_callback.ZocaloTrigger",
    autospec=True,
)
@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback.StoreInIspyb"
)
def test_ispyb_handler_receives_two_stops_but_only_ends_deposition_on_inner_one(
    ispyb_store, zocalo, RE: RunEngine, do_rotation_scan
):
    _, ispyb_callback = create_rotation_callbacks()
    ispyb_callback.emit_cb = None
    ispyb_callback.activity_gated_start = MagicMock(
        autospec=True, side_effect=ispyb_callback.activity_gated_start
    )
    ispyb_callback.activity_gated_stop = MagicMock(
        autospec=True, side_effect=ispyb_callback.activity_gated_stop
    )

    parent_mock = MagicMock()
    parent_mock.attach_mock(ispyb_store.return_value.end_deposition, "end_deposition")
    parent_mock.attach_mock(ispyb_callback.activity_gated_stop, "callback_stopped")

    RE.subscribe(ispyb_callback)
    RE(do_rotation_scan)

    assert ispyb_callback.activity_gated_stop.call_count == 2
    assert parent_mock.method_calls[1][0] == "end_deposition"


@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback.StoreInIspyb",
    autospec=True,
)
def test_ispyb_reuses_dcgid_on_same_sampleID(
    rotation_ispyb: MagicMock,
    RE: RunEngine,
    params: RotationScan,
    fake_create_rotation_devices,
    oav_parameters_for_rotation,
):
    ispyb_cb = RotationISPyBCallback()
    ispyb_cb.active = True
    ispyb_ids = IspybIds(data_collection_group_id=23, data_collection_ids=(45,))
    rotation_ispyb.return_value.begin_deposition.return_value = ispyb_ids

    test_cases = zip(
        [123, 123, 123, 456, 123],
        [False, True, True, False, False],
        strict=False,
    )

    last_dcgid = None

    RE.subscribe(ispyb_cb)

    for sample_id, same_dcgid in test_cases:
        params.sample_id = sample_id

        RE(
            rotation_scan(
                fake_create_rotation_devices, params, oav_parameters_for_rotation
            )
        )

        begin_deposition_scan_data: ScanDataInfo = (
            rotation_ispyb.return_value.begin_deposition.call_args.args[1][0]
        )
        if same_dcgid:
            assert begin_deposition_scan_data.data_collection_info.parent_id is not None
            assert (
                begin_deposition_scan_data.data_collection_info.parent_id is last_dcgid
            )
        else:
            assert begin_deposition_scan_data.data_collection_info.parent_id is None

        last_dcgid = ispyb_cb.ispyb_ids.data_collection_group_id


n_images_store_id = [
    (123, False),
    (3600, True),
    (1800, True),
    (150, False),
    (500, True),
    (201, True),
    (1, False),
    (2000, True),
    (2000, True),
    (2000, True),
    (123, False),
    (3600, True),
    (1800, True),
    (123, False),
    (1800, True),
]


@pytest.mark.parametrize("n_images,store_id", n_images_store_id)
@patch(
    "mx_bluesky.hyperion.external_interaction.callbacks.rotation.ispyb_callback.StoreInIspyb",
    new=MagicMock(),
)
def test_ispyb_handler_stores_sampleid_for_full_collection_not_screening(
    n_images: int,
    store_id: bool,
    params: RotationScan,
):
    cb = RotationISPyBCallback()
    cb.active = True

    doc: RunStart = {
        "time": 0,
        "uid": "abc123",
    }

    params.sample_id = 987678
    params.scan_width_deg = n_images / 10
    if n_images < 200:
        params.ispyb_experiment_type = IspybExperimentType.CHARACTERIZATION
    assert params.num_images == n_images
    doc["subplan_name"] = CONST.PLAN.ROTATION_OUTER  # type: ignore
    doc["hyperion_parameters"] = params.model_dump_json()  # type: ignore

    cb.start(doc)
    assert (cb.last_sample_id == 987678) is store_id
