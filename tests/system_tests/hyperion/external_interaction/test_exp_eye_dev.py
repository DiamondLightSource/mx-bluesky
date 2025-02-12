from time import sleep

import pytest
from requests import get

from mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping import (
    get_proposal_and_session_from_visit_string,
)
from mx_bluesky.common.external_interaction.ispyb.exp_eye_store import (
    BLSampleStatus,
    ExpeyeInteraction,
)

from ....conftest import SimConstants


@pytest.mark.system_test
@pytest.mark.parametrize(
    "message, expected_message",
    [
        ("Oh no!", "Oh no!"),
        (
            "Long message that will be truncated " + ("*" * 255),
            "Long message that will be truncated " + ("*" * 219),
        ),
    ],
)
def test_start_and_end_robot_load(message: str, expected_message: str):
    """To confirm this test is successful go to
    https://ispyb-test.diamond.ac.uk/dc/visit/cm37235-2 and see that data is added
    when it's run.
    """
    proposal, session = get_proposal_and_session_from_visit_string(
        SimConstants.ST_VISIT
    )
    BARCODE = "test_barcode"

    expeye = ExpeyeInteraction()

    robot_action_id = expeye.start_load(
        proposal, session, SimConstants.ST_SAMPLE_ID, 40, 3
    )

    sleep(0.5)

    print(f"Created {robot_action_id}")

    test_folder = "/dls/i03/data/2024/cm37235-2/xtal_snapshots"
    oav_snapshot = test_folder + "/235855_load_after_0.0.png"
    webcam_snapshot = test_folder + "/235855_webcam.jpg"
    expeye.update_barcode_and_snapshots(
        robot_action_id, BARCODE, oav_snapshot, webcam_snapshot
    )

    sleep(0.5)

    expeye.end_load(robot_action_id, "fail", message)

    get_robot_data_url = f"{expeye._base_url}/robot-actions/{robot_action_id}"
    response = get(get_robot_data_url, auth=expeye._auth)

    assert response.ok
    response = response.json()
    assert response["robotActionId"] == robot_action_id
    assert response["status"] == "ERROR"
    assert response["sampleId"] == SimConstants.ST_SAMPLE_ID
    assert response["sampleBarcode"] == BARCODE
    assert response["message"] == expected_message


@pytest.mark.system_test
def test_update_sample_updates_the_sample_status():
    sample_handling = ExpeyeInteraction()
    output_sample = sample_handling.update_sample_status(
        SimConstants.ST_SAMPLE_ID, BLSampleStatus.ERROR_SAMPLE
    )
    expected_status = "ERROR - sample"
    assert output_sample.bl_sample_status == expected_status
    assert output_sample.container_id == SimConstants.ST_CONTAINER_ID
