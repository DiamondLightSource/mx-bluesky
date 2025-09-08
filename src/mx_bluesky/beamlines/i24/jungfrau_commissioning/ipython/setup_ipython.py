# flake8: noqa

import inspect
from collections.abc import Callable
from inspect import getmembers, isgeneratorfunction, signature
from pathlib import Path

from bluesky.run_engine import RunEngine
from dodal.beamlines import i24
from dodal.utils import collect_factories
from pydantic_extra_types.semantic_version import SemanticVersion


from mx_bluesky.beamlines.i24.jungfrau_commissioning import (
    do_darks,
    do_external_acquisition,
    do_internal_acquisition,
    rotation_scan_plan,
)
from mx_bluesky.beamlines.i24.jungfrau_commissioning.composites import (
    RotationScanComposite,
)
from mx_bluesky.common.parameters.rotation import SingleRotationScan
from bluesky.run_engine import RunEngine  # noqa: I001
from dodal.beamlines import i24
from mx_bluesky.beamlines.i24.jungfrau_commissioning.do_darks import *

from mx_bluesky.beamlines.i24.jungfrau_commissioning.rotation_scan_plan import *
from mx_bluesky.common.utils.log import do_default_logging_setup
from mx_bluesky.beamlines.i24.jungfrau_commissioning.do_darks import *
from mx_bluesky.beamlines.i24.jungfrau_commissioning.do_internal_acquisition import *


class Col:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELL = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


DIRECTORY = "/dls/i24/data/2024/cm37275-4/jungfrau_commissioning/"

welcome_message = f"""
There are a bunch of available functions. Most of them are Bluesky plans which \
should be run in the Bluesky RunEngine using the syntax {Col.CYAN}RE({Col.GREEN}\
plan_name{Col.CYAN}){Col.ENDC}.
Some functions can poke devices directly to manipulate them. You can try running \
{Col.CYAN}hlp({Col.GREEN}function_name{Col.CYAN}){Col.ENDC} for possible information.
You can also grab device objects and manipulate them yourself. The PVs of the real \
device are associated with attributes on the Ophyd device object, so you can grab \
these and use their \
{Col.CYAN}await .set(){Col.ENDC} method (on a device or a specific PV), \
{Col.CYAN} await .get_value(){Col.ENDC} (on a device or a specific PV) \
methods if needed.
Devices are best accessed through functions in the {Col.CYAN}i24{Col.ENDC} module, for \
example, to get a handle on the vertical goniometer device, you can write:
    {Col.BLUE}vgonio = i24.vgonio(){Col.ENDC}
To list all the available plans, you can run:
    {Col.BLUE}list_plans(){Col.ENDC}
{Col.CYAN}from [module] import *{Col.ENDC} has been run for all of these plans, so you \
can access them without dots.
Current plans that can be run through this interface are {Col.CYAN}do_pedestal_darks{Col.ENDC}, \
{Col.CYAN}do_darks_for_dynamic_gain_switching{Col.ENDC}, {Col.CYAN}do_internal_acquisition{Col.ENDC}, \
and {Col.CYAN}single_rotation_plan{Col.ENDC}


To list all the available devices in the {Col.CYAN}i24{Col.ENDC} module you can run:
    {Col.BLUE}list_devices(){Col.ENDC}

To run a rotation scan, you should create parameters with params = {Col.CYAN}create_rotation_scan_params(...){Col.ENDC}, then run
{Col.CYAN}run_single_rotation_scan(params){Col.ENDC}

"""


def list_devices():
    for dev in collect_factories(i24):
        print(f"    {Col.CYAN}i24.{dev}(){Col.ENDC}")


def pretty_print_module_functions(mod, indent=0):
    sq = "'"
    for name, function in [
        (k, v)
        for k, v in getmembers(mod, isgeneratorfunction)
        if v.__module__ == mod.__name__
    ]:
        print(
            " " * indent
            + f"{Col.CYAN}{name}({Col.GREEN}{str(signature(function)).replace(sq, '')[1:-1]}{Col.CYAN}){Col.ENDC}"  # noqa
        )


def list_plans():
    plan_modules = [
        do_darks,
        do_external_acquisition,
        do_internal_acquisition,
        rotation_scan_plan,
    ]
    for module in plan_modules:
        print(f"{Col.BLUE}{module.__name__}:{Col.ENDC}")
        pretty_print_module_functions(module, indent=4)


def hlp(arg: Callable | None = None):
    """When called with no arguments, displays a welcome message. Call it on a
    function to see documentation for it."""
    if arg is None:
        print(welcome_message)
    else:
        sq = "'"
        print(
            f"{Col.CYAN}{arg.__name__}({Col.GREEN}{str(signature(arg)).replace(sq, '')[1:-1]}{Col.CYAN}){Col.ENDC}"  # noqa
        )
        print(inspect.getdoc(arg))


def create_rotation_composite() -> RotationScanComposite:
    aperture = i24.aperture()
    attenuator = i24.attenuator()
    jungfrau = i24.jungfrau()
    gonio = i24.vgonio()
    synchrotron = i24.synchrotron()
    sample_shutter = i24.sample_shutter()
    zebra = i24.zebra()
    hutch_shutter = i24.shutter()
    beamstop = i24.beamstop()
    det_stage = i24.detector_motion()  # TODO add JF position to det stage device
    backlight = i24.backlight()
    dcm = i24.dcm()
    return RotationScanComposite(
        aperture,
        attenuator,
        jungfrau,
        gonio,
        synchrotron,
        sample_shutter,
        zebra,
        hutch_shutter,
        beamstop,
        det_stage,
        backlight,
        dcm,
    )


def create_rotation_scan_params(
    exposure_time_s: float,
    omega_start_deg: float,
    rotation_increment_deg: float,
    transmission_frac: float,
    shutter_opening_time_s: float,
    detector_distance_mm: float,
    storage_directory: str,
    file_name: str,
    visit: str,
    total_scan_width_deg: float = 360,
) -> SingleRotationScan:
    return SingleRotationScan(
        exposure_time_s=exposure_time_s,
        omega_start_deg=omega_start_deg,
        rotation_increment_deg=rotation_increment_deg,
        transmission_frac=transmission_frac,
        shutter_opening_time_s=shutter_opening_time_s,
        detector_distance_mm=detector_distance_mm,
        storage_directory=storage_directory,
        file_name=file_name,
        visit=visit,
        parameter_model_version=SemanticVersion(major=5),
        snapshot_directory=Path("/tmp"),
        scan_width_deg=total_scan_width_deg,
    )


"""
    Create parameters for a single rotation scan.

    Args:
        exposure_time_s: Time of detector exposure per frame.
        omega_start_deg: Starting position of the omega axis.
        rotation_increment_deg: Increments of omega for which the detector is triggered.
        transmission_frac: Desired transmission, 0-1.
        shutter_opening_time_s: Seconds taken for the fast shutter to open
        detector_distance_mm: Desired detector Z distance for the collection
        storage_directory: Directory to store data files
        file_name: Name of output file
        visit: Visit string
        total_scan_width_deg: Total omega distance covered in scan. Defaults to 360.
"""


def run_single_rotation_scan(params: SingleRotationScan):
    yield from rotation_scan_plan.single_rotation_plan(
        create_rotation_composite(), params
    )


do_default_logging_setup("i24-bluesky.log", 12231)  # Dodal graylog stream
hlp()
print(f"Creating Bluesky RunEngine with name {Col.CYAN}RE{Col.ENDC}")
RE = RunEngine({})
print("System Ready!")
