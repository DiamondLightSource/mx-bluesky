import logging
import os
from unittest.mock import MagicMock, patch

import pytest
from bluesky import RunEngine
from bluesky import plan_stubs as bps
from bluesky.preprocessors import run_decorator
from dodal.log import get_graylog_configuration, set_up_graylog_handler

from mx_bluesky.common.external_interaction.alerting import (
    Metadata,
    get_alerting_service,
    set_alerting_service,
)
from mx_bluesky.common.external_interaction.alerting.log_based_service import (
    LoggingAlertService,
)
from mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback import (
    SampleHandlingCallback,
)
from mx_bluesky.hyperion.parameters.constants import CONST, HyperionConstants

from .....conftest import SimConstants


@pytest.fixture(autouse=True)
def setup_graylog():
    logger = logging.getLogger("Dodal")
    host, _ = get_graylog_configuration(False)
    set_up_graylog_handler(logger, host, HyperionConstants.GRAYLOG_PORT)


@pytest.fixture
def patch_raise_alert_to_disable_ehc_notifications():
    """Patch raise_alert so that TEST is prepended to the alert summary to avoid downstream
    email filters from forwarding to the EHC"""

    def patched_raise_alert(summary: str, content: str, metadata: dict[Metadata, str]):
        return get_alerting_service().raise_alert("TEST " + summary, content, metadata)

    with patch(
        "mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback"
        ".get_alerting_service",
        return_value=MagicMock(**{"raise_alert.side_effect": patched_raise_alert}),
    ):
        yield


@pytest.mark.requires(external="graylog")
def test_alert_to_graylog():
    alert_service = LoggingAlertService(CONST.GRAYLOG_STREAM_ID)
    alert_service.raise_alert(
        "Test alert", "This is a test.", {Metadata.SAMPLE_ID: "12345"}
    )


@patch(
    "mx_bluesky.common.external_interaction.callbacks.sample_handling.sample_handling_callback.ExpeyeInteraction",
    MagicMock(),
)
@pytest.mark.requires(external="graylog")
@patch.dict(os.environ, {"BEAMLINE": "i03"})
def test_alert_from_plan_exception(
    RE: RunEngine, patch_raise_alert_to_disable_ehc_notifications
):
    RE.subscribe(SampleHandlingCallback())
    set_alerting_service(LoggingAlertService(CONST.GRAYLOG_STREAM_ID))

    @run_decorator(
        md={
            "activate_callbacks": ["SampleHandlingCallback"],
            "metadata": {
                "sample_id": SimConstants.ST_SAMPLE_ID,
                "visit": SimConstants.ST_VISIT,
                "container": SimConstants.ST_CONTAINER_ID,
            },
        }
    )
    def plan_with_exception():
        yield from bps.null()
        raise RuntimeError("Test exception.")

    with pytest.raises(RuntimeError):
        RE(plan_with_exception())
