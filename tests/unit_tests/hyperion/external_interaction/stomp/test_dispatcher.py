from unittest.mock import MagicMock, Mock

import pytest
from blueapi.core import DataEvent
from bluesky_stomp.messaging import MessageContext, StompClient

from mx_bluesky.hyperion.external_interaction.callbacks.stomp.dispatcher import (
    StompDispatcher,
)

TEST_TASK_ID = "TEST_TASK_ID"

TEST_SUB_ID = "SUB_ID"


@pytest.fixture
def mock_client():
    stomp_client = Mock(spec=StompClient)
    stomp_client.subscribe.return_value = TEST_SUB_ID
    return stomp_client


def test_dispatcher_connect_and_disconnects_on_enter_and_exit(mock_client):
    dispatcher = StompDispatcher(mock_client)
    with dispatcher:
        mock_client.connect.assert_called_once()
        mock_client.subscribe.assert_called_once()
    mock_client.unsubscribe.assert_called_once_with(TEST_SUB_ID)
    mock_client.disconnect.assert_called_once()


def test_dispatcher_forwards_data_event(mock_client, test_event_data):
    dispatcher = StompDispatcher(mock_client)
    callback = MagicMock()

    with dispatcher:
        stomp_subs_callback = mock_client.subscribe.mock_calls[0].args[1]
        dispatcher.subscribe(callback)
        stomp_subs_callback(
            DataEvent(
                name="start",
                doc=test_event_data.test_grid_detect_and_gridscan_start_document,
                task_id=TEST_TASK_ID,
            ),
            Mock(spec=MessageContext),
        )
        callback.assert_called_once_with(
            "start", test_event_data.test_grid_detect_and_gridscan_start_document
        )
