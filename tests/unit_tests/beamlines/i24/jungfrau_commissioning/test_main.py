from unittest.mock import MagicMock, patch

from mx_bluesky.beamlines.i24.jungfrau_commissioning.__main__ import hlp


@patch("builtins.print")
def test_hlp(mock_print: MagicMock):
    hlp()
    assert "There are a bunch of available functions." in mock_print.call_args.args[0]
    hlp(hlp)
    assert (
        "When called with no arguments, displays a welcome message."
        in mock_print.call_args.args[0]
    )
