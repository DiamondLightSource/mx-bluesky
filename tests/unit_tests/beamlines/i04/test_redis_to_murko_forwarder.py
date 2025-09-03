import io
import json
import pickle
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest
from PIL import Image

from mx_bluesky.beamlines.i04.redis_to_murko_forwarder import (
    MURKO_ADDRESS,
    BatchMurkoForwarder,
    MurkoRequest,
    RedisListener,
    get_image_size,
    send_to_murko_and_get_results,
)


@pytest.fixture
def batch_forwarder():
    return BatchMurkoForwarder(redis_client=MagicMock(), batch_size=3)


@pytest.fixture
@patch("mx_bluesky.beamlines.i04.redis_to_murko_forwarder.StrictRedis")
def redis_listener(mock_redis):
    return RedisListener()


def test_given_image_added_when_flush_called_then_murko_called(
    batch_forwarder: BatchMurkoForwarder,
):
    batch_forwarder._handle_batch_of_images = MagicMock()
    batch_forwarder.add("sample_1", "uuid_1", np.zeros((256, 320)))
    batch_forwarder.flush()
    batch_forwarder._handle_batch_of_images.assert_called_once()


def test_given_no_image_added_when_flush_called_then_murko_not_called(
    batch_forwarder: BatchMurkoForwarder,
):
    batch_forwarder._handle_batch_of_images = MagicMock()
    batch_forwarder.flush()
    batch_forwarder._handle_batch_of_images.assert_not_called()


def test_given_already_flushed_when_flush_called_again_then_murko_not_called_twice(
    batch_forwarder: BatchMurkoForwarder,
):
    batch_forwarder._handle_batch_of_images = MagicMock()
    batch_forwarder.add("sample_1", "uuid_1", np.zeros((256, 320)))
    batch_forwarder.flush()
    batch_forwarder._handle_batch_of_images.assert_called_once()
    batch_forwarder._handle_batch_of_images.reset_mock()
    batch_forwarder.flush()
    batch_forwarder._handle_batch_of_images.assert_not_called()


def test_when_image_with_new_size_added_then_murko_called(
    batch_forwarder: BatchMurkoForwarder,
):
    batch_forwarder._handle_batch_of_images = MagicMock()
    batch_forwarder.add("sample_1", "uuid_1", np.zeros((256, 320)))
    batch_forwarder._handle_batch_of_images.assert_not_called()
    batch_forwarder.add("sample_1", "uuid_2", np.zeros((256, 450)))
    batch_forwarder._handle_batch_of_images.assert_called_once()


def test_when_more_images_added_than_batch_size_then_murko_called(
    batch_forwarder: BatchMurkoForwarder,
):
    batch_forwarder._handle_batch_of_images = MagicMock()
    for i in range(3):
        batch_forwarder.add("sample_1", f"uuid_{i}", np.zeros((256, 320)))

    batch_forwarder._handle_batch_of_images.assert_called_once()


def test_when_results_sent_to_redis_then_set_on_multiple_keys_but_published_once(
    batch_forwarder: BatchMurkoForwarder,
):
    results = [("uuid_1", {"result": 1}), ("uuid_2", {"result": 2})]
    batch_forwarder._send_murko_results_to_redis("sample_id", results)

    assert batch_forwarder.redis_client.hset.call_args_list == [  # type:ignore
        call(
            "murko:sample_id:results",
            "uuid_1",
            str(pickle.dumps({"result": 1})),
        ),
        call(
            "murko:sample_id:results",
            "uuid_2",
            str(pickle.dumps({"result": 2})),
        ),
    ]
    batch_forwarder.redis_client.publish.assert_called_once_with(  # type:ignore
        "murko-results", pickle.dumps(results)
    )


@patch(
    "mx_bluesky.beamlines.i04.redis_to_murko_forwarder.send_to_murko_and_get_results"
)
def test_when_images_flushed_then_results_are_gathered_correlated_and_sent_to_redis(
    mock_get_results: MagicMock, batch_forwarder: BatchMurkoForwarder
):
    mock_get_results.return_value = {
        "descriptions": [
            {"most_likely_click": (0, 1)},
            {"most_likely_click": (0.5, 0.75)},
        ]
    }
    batch_forwarder.add("sample_1", "uuid_1", np.zeros((256, 320)))
    batch_forwarder.add("sample_1", "uuid_2", np.zeros((256, 320)))
    batch_forwarder.flush()

    assert batch_forwarder.redis_client.hset.call_args_list == [  # type:ignore
        call(
            "murko:sample_1:results",
            "uuid_1",
            str(pickle.dumps({"most_likely_click": (0, 1)})),
        ),
        call(
            "murko:sample_1:results",
            "uuid_2",
            str(pickle.dumps({"most_likely_click": (0.5, 0.75)})),
        ),
    ]


def test_get_image_size_gives_expected_size():
    image = Image.new("RGB", (256, 512), color="white")
    image = np.asarray(image)
    width, height = get_image_size(image)
    assert width == 256
    assert height == 512


def test_when_listen_for_data_called_on_redis_listener_then_subscribes_to_expected_channel(
    redis_listener: RedisListener,
):
    # Raise exception to exit the infinite loop
    redis_listener._get_and_handle_message = MagicMock(side_effect=TimeoutError())

    with pytest.raises(TimeoutError):
        redis_listener.listen_for_image_data_forever()

    redis_listener.redis_client.pubsub().subscribe.assert_called_once_with("murko")  # type:ignore


def test_given_no_message_received_then_forwarder_flushed(
    redis_listener: RedisListener,
):
    redis_listener.forwarder = MagicMock()
    redis_listener.pubsub.get_message.return_value = None  # type:ignore
    redis_listener._get_and_handle_message()
    redis_listener.forwarder.flush.assert_called_once()


def get_jpeg_image():
    img = Image.new("RGB", (1, 1), color="black")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    return img_byte_arr.getvalue()


def test_given_jpeg_image_received_then_data_retrieved_from_correct_redis_key(
    redis_listener: RedisListener,
):
    redis_listener.forwarder = MagicMock()
    data = {"uuid": "uuid_1", "sample_id": "sample_id_1"}
    redis_listener.pubsub.get_message.return_value = {  # type:ignore
        "type": "message",
        "data": json.dumps(data),
    }
    redis_listener.redis_client.hget.return_value = get_jpeg_image()  # type:ignore
    redis_listener._get_and_handle_message()
    redis_listener.redis_client.hget.assert_called_once_with(  # type:ignore
        "murko:sample_id_1:raw", "uuid_1"
    )


def test_given_jpeg_image_received_then_converted_to_numpy_array_and_sent_to_forwarder(
    redis_listener: RedisListener,
):
    redis_listener.forwarder = MagicMock()
    data = {"uuid": "uuid_1", "sample_id": "sample_id_1"}
    redis_listener.pubsub.get_message.return_value = {  # type:ignore
        "type": "message",
        "data": json.dumps(data),
    }
    redis_listener.redis_client.hget.return_value = get_jpeg_image()  # type:ignore
    redis_listener._get_and_handle_message()

    add_call = redis_listener.forwarder.add.call_args_list[0][0]  # type:ignore

    assert add_call[0] == "sample_id_1"
    assert add_call[1] == "uuid_1"
    assert np.array_equal(add_call[2], np.array([[[0, 0, 0]]]))


@patch("mx_bluesky.beamlines.i04.redis_to_murko_forwarder.zmq")
def test_send_to_murko_and_get_results_calls_murko_as_expected(patch_zmq):
    mock_request: MurkoRequest = {"prefix": "test"}  # type: ignore

    mock_socket = patch_zmq.Context.return_value.socket.return_value
    expected_return_dict = {"descriptions": ["returned"]}
    mock_socket.recv.return_value = pickle.dumps(expected_return_dict)

    returned = send_to_murko_and_get_results(mock_request)

    mock_socket.connect.assert_called_once_with(MURKO_ADDRESS)
    mock_socket.send.assert_called_once_with(pickle.dumps(mock_request))
    assert returned == expected_return_dict


@patch("mx_bluesky.beamlines.i04.redis_to_murko_forwarder.LOGGER")
def test_given_no_bytes_received_then_warn_and_do_nothing(
    patch_logger: MagicMock,
    redis_listener: RedisListener,
):
    redis_listener.forwarder = MagicMock()
    data = {"uuid": "uuid_1", "sample_id": "sample_id_1"}
    redis_listener.pubsub.get_message.return_value = {  # type:ignore
        "type": "message",
        "data": json.dumps(data),
    }
    redis_listener.redis_client.hget.return_value = None  # type:ignore
    redis_listener._get_and_handle_message()

    patch_logger.warning.assert_called_once()
    redis_listener.forwarder.add.assert_not_called()  # type:ignore
