import configparser
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from event_model.documents import Event
from requests import JSONDecodeError, patch, post
from requests.auth import AuthBase

from mx_bluesky.common.external_interaction.ispyb.ispyb_utils import (
    get_current_time_string,
    get_ispyb_config,
)
from mx_bluesky.common.utils.exceptions import ISPyBDepositionNotMadeError

RobotActionID = int


class BearerAuth(AuthBase):
    def __init__(self, token):
        self.token = token

    def __call__(self, r):
        r.headers["authorization"] = "Bearer " + self.token
        return r


def _get_base_url_and_token() -> tuple[str, str]:
    config = configparser.ConfigParser()
    conf = get_ispyb_config()
    config.read(conf)
    expeye_config = config["expeye"]
    return expeye_config["url"], expeye_config["token"]


def _send_and_get_response(auth, url, data, send_func) -> dict:
    response = send_func(url, auth=auth, json=data)
    if not response.ok:
        try:
            resp_txt = str(response.json())
        except JSONDecodeError:
            resp_txt = str(response)
        raise ISPyBDepositionNotMadeError(
            f"Could not write {data} to {url}: {resp_txt}"
        )
    return response.json()


@dataclass
class BLSample:
    container_id: int
    bl_sample_id: int
    bl_sample_status: str | None


class BLSampleStatus(StrEnum):
    # The sample has been loaded
    LOADED = "LOADED"
    # Problem with the sample e.g. pin too long/short
    ERROR_SAMPLE = "ERROR - sample"
    # Any other general error
    ERROR_BEAMLINE = "ERROR - beamline"


assert all(len(value) <= 20 for value in BLSampleStatus), (
    "Column size limit of 20 for BLSampleStatus"
)


def create_update_data_from_event_doc(
    mapping: dict[str, str], event: Event
) -> dict[str, Any]:
    """Given a mapping between bluesky event data and an event itself this function will
    create a dict that can be used to update exp-eye."""
    event_data = event["data"]
    return {
        target_key: event_data[source_key]
        for source_key, target_key in mapping.items()
        if source_key in event_data
    }


class ExpeyeInteraction:
    """Exposes functionality from the Expeye core API"""

    CREATE_ROBOT_ACTION = "/proposals/{proposal}/sessions/{visit_number}/robot-actions"
    UPDATE_ROBOT_ACTION = "/robot-actions/{action_id}"

    def __init__(self) -> None:
        url, token = _get_base_url_and_token()
        self._base_url = url
        self._auth = BearerAuth(token)

    def start_robot_action(
        self,
        action_type: Literal["LOAD", "UNLOAD"],
        proposal_reference: str,
        visit_number: int,
        sample_id: int,
    ) -> RobotActionID:
        """Create a robot action entry in ispyb.

        Args:
            action_type ("LOAD" | "UNLOAD"): The robot action being performed
            proposal_reference (str): The proposal of the experiment e.g. cm37235
            visit_number (int): The visit number for the proposal, usually this can be
                                found added to the end of the proposal e.g. the data for
                                visit number 2 of proposal cm37235 is in cm37235-2
            sample_id (int): The id of the sample in the database

        Returns:
            RobotActionID: The id of the robot load action that is created
        """
        url = self._base_url + self.CREATE_ROBOT_ACTION.format(
            proposal=proposal_reference, visit_number=visit_number
        )

        data = {
            "startTimestamp": get_current_time_string(),
            "actionType": action_type,
            "sampleId": sample_id,
        }
        response = _send_and_get_response(self._auth, url, data, post)
        return response["robotActionId"]

    def update_robot_action(
        self,
        action_id: RobotActionID,
        data: dict[str, Any],
    ):
        """Update an existing robot action to contain additional info.

        Args:
            action_id (RobotActionID): The id of the action to update
            data (dict): The data to update with, where the keys match those expected
                         by exp-eye.
        """
        url = self._base_url + self.UPDATE_ROBOT_ACTION.format(action_id=action_id)
        _send_and_get_response(self._auth, url, data, patch)

    def end_robot_action(self, action_id: RobotActionID, status: str, reason: str):
        """Finish an existing robot action, providing final information about how it went

        Args:
            action_id (RobotActionID): The action to finish.
            status (str): The status of the action at the end, "success" for success,
                          otherwise error
            reason (str): If the status is in error than the reason for that error
        """
        url = self._base_url + self.UPDATE_ROBOT_ACTION.format(action_id=action_id)

        run_status = "SUCCESS" if status == "success" else "ERROR"

        data = {
            "endTimestamp": get_current_time_string(),
            "status": run_status,
            "message": reason[:255] if reason else "",
        }
        _send_and_get_response(self._auth, url, data, patch)

    def update_sample_status(
        self, bl_sample_id: int, bl_sample_status: BLSampleStatus
    ) -> BLSample:
        """Update the blSampleStatus of a sample.
        Args:
            bl_sample_id: The sample ID
            bl_sample_status: The sample status
            status_message: An optional message
        Returns:
             The updated sample
        """
        data = {"blSampleStatus": (str(bl_sample_status))}
        response = _send_and_get_response(
            self._auth, self._base_url + f"/samples/{bl_sample_id}", data, patch
        )
        return self._sample_from_json(response)

    def _sample_from_json(self, response) -> BLSample:
        return BLSample(
            bl_sample_id=response["blSampleId"],
            bl_sample_status=response["blSampleStatus"],
            container_id=response["containerId"],
        )
