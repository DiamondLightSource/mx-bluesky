import bluesky.plan_stubs as bps

from mx_bluesky.common.utils.log import LOGGER


def hello():
    """Plan to log 'Hello World' to the GDA log panel via Bluesky logging."""
    LOGGER.info("Hello World from I23 Bluesky plan!")

    # Example: Read a value and log it
    yield from bps.sleep(0.1)  # Yield to Bluesky to keep it a valid plan
    LOGGER.info("Plan completed successfully")
