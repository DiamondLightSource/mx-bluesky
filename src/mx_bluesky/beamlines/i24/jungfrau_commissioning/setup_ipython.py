# flake8: noqa

# This file runs in the iPython session on startup

from pathlib import Path

from bluesky.run_engine import RunEngine
from dodal.beamlines import i24

from mx_bluesky.beamlines.i24.jungfrau_commissioning.main import (
    hlp,
    list_devices,
    list_plans,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.gain_mode_darks_plans import *
from mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.jungfrau_plans import *
from mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.rotation_scan_plans import *
from mx_bluesky.beamlines.i24.jungfrau_commissioning.plans.zebra_plans import *
from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.log import (
    set_up_logging_handlers,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils import text_colors as col

DIRECTORY = "/dls/i24/data/2024/cm37275-4/jungfrau_commissioning/"


set_up_logging_handlers()
hlp()
print(f"Creating Bluesky RunEngine with name {col.CYAN}RE{col.ENDC}")
RE = RunEngine({})
print("System Ready!")
