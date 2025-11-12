import json
from unittest.mock import MagicMock

import pytest
from event_model import Event

from mx_bluesky.beamlines.i04.callbacks.murko_callback import (
    MurkoCallback,
    extrapolate_omega,
)

test_oav_uuid = "UUID"
test_smargon_data = 90


def event_template(data_key, data_value, timestamp=1666604299.0) -> Event:
    return {
        "descriptor": "bd45c2e5-2b85-4280-95d7-a9a15800a78b",
        "time": 1666604299.01,
        "data": {data_key: data_value},
        "timestamps": {data_key: timestamp},
        "seq_num": 1,
        "uid": "29033ecf-e052-43dd-98af-c7cdd62e8173",
        "filled": {},
    }


test_oav_event = event_template("oav_to_redis_forwarder-uuid", test_oav_uuid)
test_smargon_event = event_template("smargon-omega", test_smargon_data)

test_start_document = {
    "uid": "event_uuid",
    "zoom_percentage": 80,
    "microns_per_x_pixel": 1.2,
    "microns_per_y_pixel": 2.5,
    "beam_centre_i": 158,
    "beam_centre_j": 452,
    "sample_id": 12345,
}


@pytest.fixture
def murko_callback() -> MurkoCallback:
    callback = MurkoCallback("", "")
    callback.redis_client = MagicMock()
    return callback


@pytest.fixture
def murko_with_mock_call(murko_callback) -> MurkoCallback:
    murko_callback.call_murko = MagicMock()
    return murko_callback


def test_when_oav_data_arrives_then_murko_not_called(
    murko_with_mock_call: MurkoCallback,
):
    murko_with_mock_call.event(test_oav_event)
    murko_with_mock_call.call_murko.assert_not_called()  # type: ignore


def test_when_smargon_data_arrives_with_no_image_then_murko_not_called(
    murko_with_mock_call: MurkoCallback,
):
    murko_with_mock_call.event(test_smargon_event)
    murko_with_mock_call.call_murko.assert_not_called()  # type: ignore


def test_when_smargon_data_arrives_then_image_data_then_murko_not_called(
    murko_with_mock_call: MurkoCallback,
):
    murko_with_mock_call.event(test_smargon_event)
    murko_with_mock_call.event(test_oav_event)
    murko_with_mock_call.call_murko.assert_not_called()  # type: ignore


def test_given_image_data_when_first_two_sets_of_smargon_data_arrive_then_murko_called_with_latest_image_and_omega(
    murko_with_mock_call: MurkoCallback,
):
    murko_with_mock_call.event(test_oav_event)
    murko_with_mock_call.event(test_smargon_event)
    murko_with_mock_call.call_murko.assert_called_once_with(  # type: ignore
        test_oav_uuid, test_smargon_data
    )

    murko_with_mock_call.call_murko.reset_mock()  # type: ignore

    murko_with_mock_call.event(event_template("smargon-omega", second_omega := 30))
    murko_with_mock_call.call_murko.assert_called_once_with(  # type: ignore
        test_oav_uuid, second_omega
    )


def test_given_two_sets_of_smargon_data_then_next_image_calls_murko_with_extrapolated_omega(
    murko_with_mock_call: MurkoCallback,
):
    murko_with_mock_call.event(test_oav_event)
    murko_with_mock_call.event(event_template("smargon-omega", 10, 0))
    murko_with_mock_call.event(event_template("smargon-omega", 15, 5))

    murko_with_mock_call.call_murko.reset_mock()  # type:ignore

    murko_with_mock_call.event(
        event_template("oav_to_redis_forwarder-uuid", test_oav_uuid, 10)
    )

    murko_with_mock_call.call_murko.assert_called_once_with(test_oav_uuid, 20)  # type: ignore


def test_given_three_sets_of_smargon_data_then_next_image_calls_murko_with_extrapolated_omega_from_last_two(
    murko_with_mock_call: MurkoCallback,
):
    murko_with_mock_call.event(test_oav_event)
    murko_with_mock_call.event(event_template("smargon-omega", 10, 0))
    murko_with_mock_call.event(event_template("smargon-omega", 15, 5))
    murko_with_mock_call.event(event_template("smargon-omega", 17, 6))

    murko_with_mock_call.call_murko.reset_mock()  # type:ignore

    murko_with_mock_call.event(
        event_template("oav_to_redis_forwarder-uuid", test_oav_uuid, 10)
    )

    murko_with_mock_call.call_murko.assert_called_once_with(test_oav_uuid, 25)  # type: ignore


def test_when_murko_called_with_event_data_then_meta_data_put_in_redis(
    murko_callback: MurkoCallback,
):
    murko_callback.start(test_start_document)  # type: ignore
    murko_callback.event(test_oav_event)
    murko_callback.event(test_smargon_event)

    expected_metadata = {
        "zoom_percentage": 80,
        "microns_per_x_pixel": 1.2,
        "microns_per_y_pixel": 2.5,
        "beam_centre_i": 158,
        "beam_centre_j": 452,
        "sample_id": 12345,
        "omega_angle": test_smargon_data,
        "uuid": test_oav_uuid,
    }

    murko_callback.redis_client.hset.assert_called_once_with(  # type: ignore
        "murko:12345:metadata", test_oav_uuid, json.dumps(expected_metadata)
    )
    murko_callback.redis_client.publish.assert_called_once_with(  # type: ignore
        "murko", json.dumps(expected_metadata)
    )


@pytest.mark.parametrize(
    "latest_omega, previous_omega, now, expected",
    [
        # Standard case
        (
            {"value": 10.0, "timestamp": 100.0},
            {"value": 5.0, "timestamp": 90.0},
            110.0,
            15.0,
        ),
        # Crossing zero from negative to positive
        (
            {"value": -5.0, "timestamp": 100.0},
            {"value": -15.0, "timestamp": 90.0},
            110.0,
            5.0,
        ),
        (
            {"value": 10.0, "timestamp": 100.0},
            {"value": -5.0, "timestamp": 90.0},
            110.0,
            25.0,
        ),
        # Crossing zero from positive to negative
        (
            {"value": 5.0, "timestamp": 100.0},
            {"value": 15.0, "timestamp": 90.0},
            110.0,
            -5.0,
        ),
        # Large time gaps between readings
        (
            {"value": 50.0, "timestamp": 500.0},
            {"value": 40.0, "timestamp": 400.0},
            600.0,
            60.0,
        ),
        # Very small time differences
        (
            {"value": 10.0, "timestamp": 100.0},
            {"value": 9.9, "timestamp": 99.99},
            100.01,
            10.1,
        ),
        # Identical omega values (should remain constant)
        (
            {"value": 30.0, "timestamp": 200.0},
            {"value": 30.0, "timestamp": 190.0},
            210.0,
            30.0,
        ),
    ],
)
def test_extrapolate_omega(latest_omega, previous_omega, now, expected):
    assert extrapolate_omega(latest_omega, previous_omega, now) == expected
