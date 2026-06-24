import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator

from mx_bluesky.common.utils.log import LOGGER


def test_logging() -> MsgGenerator:
    """Plan to log to the GDA log panel via Bluesky logging."""
    LOGGER.info("Testing I23 Bluesky logging.")
    print("This is a print statement.")
    yield from bps.sleep(0.1)
    LOGGER.info("Plan completed successfully.")
    raise RuntimeError("This is a plan error")
