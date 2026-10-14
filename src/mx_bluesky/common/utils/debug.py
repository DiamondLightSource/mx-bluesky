from debugpy import listen, wait_for_client

from mx_bluesky.common.utils.log import LOGGER


def enable_debugging(wait_for_attach: bool, port: int):
    """Enable debugging via debugpy
    Args:
        wait_for_attach (bool): True to wait for the debugger to attach
        port (int): Port on which to listen."""
    listen(("0.0.0.0", port))
    LOGGER.info(f"Listening for debugger connections on {port}")
    if wait_for_attach:
        LOGGER.info("Waiting for debugger to attach...")
        wait_for_client()
