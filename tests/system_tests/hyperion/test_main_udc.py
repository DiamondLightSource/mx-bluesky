from unittest.mock import MagicMock, patch

import pytest
from blueapi.core import BlueskyContext
from dodal.devices.baton import Baton
from ophyd_async.testing import set_mock_value

from mx_bluesky.common.utils.context import find_device_in_context
from mx_bluesky.hyperion.__main__ import main
from mx_bluesky.hyperion.baton_handler import HYPERION_USER


@pytest.fixture(autouse=True)
def patch_setup_devices():
    from mx_bluesky.hyperion.utils.context import setup_devices

    def patched_setup_devices(context: BlueskyContext, dev_mode: bool):
        setup_devices(context, True)
        if not isinstance(context.run_engine, MagicMock):
            # reapply requested user to the newly created fake baton
            # but not if it's a magicmock
            baton_with_requested_user(context, HYPERION_USER)

    # Patch setup_devices to patch the baton again when it is re-created
    with (
        patch(
            "mx_bluesky.hyperion.baton_handler.setup_devices",
            side_effect=patched_setup_devices,
        ) as patched_func,
        patch(
            "mx_bluesky.hyperion.utils.context.setup_devices",
            side_effect=patched_setup_devices,
        ),
    ):
        yield patched_func


def baton_with_requested_user(
    bluesky_context: BlueskyContext, user: str = HYPERION_USER
) -> Baton:
    baton = find_device_in_context(bluesky_context, "baton", Baton)
    set_mock_value(baton.requested_user, user)
    return baton


@pytest.mark.requires(external="fake_agamemnon")
@patch.dict(
    "os.environ", {"AGAMEMNON_URL": "http://localhost:8088/", "BEAMLINE": "i03"}
)
@patch("sys.argv", new=["hyperion", "--dev", "--mode", "udc"])
@pytest.mark.timeout(0)
def test_udc_mode():
    """
    Run Hyperion in UDC mode against a fake agamemnon server, to test the API.
    One is provided in the hyperion-system-test project, that just continually serves a wait command."""
    main()
