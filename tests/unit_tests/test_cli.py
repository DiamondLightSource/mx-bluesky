import subprocess
import sys

import pytest

from mx_bluesky import __version__


@pytest.mark.skip_in_pycharm(reason="subprocess returns tty escape sequences")
def test_cli_version():
    cmd = [sys.executable, "-m", "mx_bluesky", "--version"]
    assert subprocess.check_output(cmd).decode().strip() == __version__
