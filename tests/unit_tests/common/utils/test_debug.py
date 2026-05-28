from unittest.mock import MagicMock, patch

from mx_bluesky.common.utils.debug import enable_debugging


@patch("mx_bluesky.common.utils.debug.listen")
@patch("mx_bluesky.common.utils.debug.wait_for_client")
def test_enable_debugging_no_wait(
    mock_wait_for_client: MagicMock,
    mock_listen: MagicMock,
):
    enable_debugging(False, 1234)
    mock_listen.assert_called_once_with(("0.0.0.0", 1234))
    mock_wait_for_client.assert_not_called()


@patch("mx_bluesky.common.utils.debug.listen")
@patch("mx_bluesky.common.utils.debug.wait_for_client")
def test_enable_debugging_wait(
    mock_wait_for_client: MagicMock,
    mock_listen: MagicMock,
):
    enable_debugging(True, 1234)
    mock_listen.assert_called_once_with(("0.0.0.0", 1234))
    mock_wait_for_client.assert_called_once()
