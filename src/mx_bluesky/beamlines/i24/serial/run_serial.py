import argparse
import logging
import subprocess
from os import environ
from pathlib import Path

logger = logging.getLogger("I24ssx.run")


def _parse_input(expt: str):
    parser = argparse.ArgumentParser(description=f"Run a {expt} collection.")
    parser.add_argument("-t", "--test", action="store_true", help="Run in test mode.")
    args = parser.parse_args()
    return args


def get_location(default: str = "dev") -> str:
    return environ.get("BEAMLINE") or default


def get_edm_path() -> Path:
    return Path(__file__).parents[5] / "edm_serial"


def _get_file_path() -> Path:
    return Path(__file__).parent


def run_extruder():
    args = _parse_input("extruder")
    loc = get_location()
    logger.debug(f"Running on {loc}.")
    edm_path = get_edm_path()
    filepath = _get_file_path()
    test_mode = "--test" if args.test else ""
    logger.debug(f"Running {filepath}/run_extruder.sh")
    subprocess.run(
        ["bash", filepath / "run_extruder.sh", edm_path.as_posix(), test_mode]
    )


def run_fixed_target():
    args = _parse_input("fixed target")
    loc = get_location()
    logger.info(f"Running on {loc}.")
    edm_path = get_edm_path()
    filepath = _get_file_path()
    test_mode = "--test" if args.test else ""
    logger.debug(f"Running {filepath}/run_fixed_target.sh")
    subprocess.run(
        ["bash", filepath / "run_fixed_target.sh", edm_path.as_posix(), test_mode]
    )
