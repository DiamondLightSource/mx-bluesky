import pickle
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from numpy.testing import assert_array_equal

from mx_bluesky.beamlines.i04.murko.stream_data_to_murko import (
    RedisMurkoForwarder,
    convert_result_to_pixels,
    create_murko_request,
)

TWO_BY_TWO_IMAGE = np.array([[[1, 2, 3], [4, 5, 6]], [[7, 8, 9], [1, 2, 3]]])


def test_when_create_murko_request_called_then_returns_expected_request():
    images = {"1": TWO_BY_TWO_IMAGE, "2": TWO_BY_TWO_IMAGE}

    request = create_murko_request(images)

    assert_array_equal(
        request["to_predict"], np.asarray([TWO_BY_TWO_IMAGE, TWO_BY_TWO_IMAGE])
    )
    assert request["to_predict"].shape == (2, 2, 2, 3)
    assert request["prefix"] == ["1", "2"]
    assert not request["save"]


@pytest.mark.parametrize(
    "resolution, murko_result, expected",
    [((1024, 768), (1, 1), (1024, 768)), ((100, 100), (0.5, 0.75), (50, 75))],
)
def test_convert_results_to_pixels_gives_expected_output(
    resolution, murko_result, expected
):
    image = np.zeros(resolution)
    pixel_coords = convert_result_to_pixels(murko_result, image)
    assert pixel_coords == expected


@patch("mx_bluesky.beamlines.i04.murko.stream_data_to_murko.zmq")
def test_send_and_receive_results_from_murko(patch_zmq):
    patch_zmq.Context.return_value = (patch_context := MagicMock())
    patch_context.socket.return_value = (patch_socket := MagicMock())
    patch_socket.recv.return_value = pickle.dumps(test_result := {"test_result": True})

    test_request = {"test_request": True}

    forwarder = RedisMurkoForwarder("test_murko_connection")
    result = forwarder._send_request_to_murko_and_return_results(test_request)

    patch_socket.connect.assert_called_once_with("test_murko_connection")
    patch_socket.send.assert_called_once_with(pickle.dumps(test_request))
    assert result == test_result
