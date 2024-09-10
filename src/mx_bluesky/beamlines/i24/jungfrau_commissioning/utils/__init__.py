from datetime import datetime
from pathlib import Path

from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.log import LOGGER


class text_colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELL = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def date_time_string():
    return datetime.now().strftime("%Y-%m-%d-%H-%M-%S")


def run_number(directory: Path):
    with open(directory / "run_number.txt") as f:
        run_number = int(f.read())
        LOGGER.info(f"current run number: {run_number+1}")
    with open(directory / "run_number.txt", "w") as f:
        f.write(f"{run_number+1:05d}")
    return run_number + 1
