from unittest.mock import MagicMock, patch

from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from bluesky.run_engine import RunEngine

from mx_bluesky.common.external_interaction.alerting import Metadata
from mx_bluesky.common.external_interaction.callbacks.udc.alert_on_container_change import (
    AlertOnContainerChange,
)

TEST_SAMPLE_ID = 10
TEST_VISIT = "cm1234-67"


def dummy_plan_with_container(container: int):
    def my_plan():
        yield from bps.null()

    yield from bpp.run_wrapper(
        my_plan(),
        md={
            "metadata": {
                "container": container,
                "sample_id": TEST_SAMPLE_ID,
                "visit": TEST_VISIT,
            },
            "activate_callbacks": ["AlertOnContainerChange"],
        },
    )


@patch.dict("os.environ", {"BEAMLINE": "i03"})
def test_given_callback_just_initialised_then_alerts_on_first_container(
    RE: RunEngine, mock_alert_service: MagicMock
):
    RE.subscribe(AlertOnContainerChange())

    RE(dummy_plan_with_container(5))

    mock_alert_service.raise_alert.assert_called_once_with(
        "UDC moved on to puck 5 on i03",
        "Hyperion finished container None and moved on to 5",
        {
            Metadata.SAMPLE_ID: "10",
            Metadata.VISIT: "cm1234-67",
            Metadata.CONTAINER: "5",
        },
    )


@patch.dict("os.environ", {"BEAMLINE": "i03"})
def test_when_data_collected_on_the_same_container_then_only_alerts_for_first_one(
    RE: RunEngine, mock_alert_service: MagicMock
):
    RE.subscribe(AlertOnContainerChange())

    RE(dummy_plan_with_container(5))

    mock_alert_service.reset_mock()

    RE(dummy_plan_with_container(5))
    RE(dummy_plan_with_container(5))
    RE(dummy_plan_with_container(5))

    mock_alert_service.raise_alert.assert_not_called()


@patch.dict("os.environ", {"BEAMLINE": "i03"})
def test_when_data_collected_on_new_container_then_only_alerts(
    RE: RunEngine, mock_alert_service: MagicMock
):
    RE.subscribe(AlertOnContainerChange())

    RE(dummy_plan_with_container(5))

    mock_alert_service.reset_mock()

    RE(dummy_plan_with_container(10))

    mock_alert_service.raise_alert.assert_called_once_with(
        "UDC moved on to puck 10 on i03",
        "Hyperion finished container 5 and moved on to 10",
        {
            Metadata.SAMPLE_ID: "10",
            Metadata.VISIT: "cm1234-67",
            Metadata.CONTAINER: "10",
        },
    )
