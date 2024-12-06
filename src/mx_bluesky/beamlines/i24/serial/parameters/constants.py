from enum import Enum
from os import environ
from pathlib import Path

from mx_bluesky.beamlines.i24.serial.log import _read_visit_directory_from_file


class SSXType(Enum):
    FIXED = "Serial Fixed"
    EXTRUDER = "Serial Jet"


BEAM_CENTER_POS: dict[str, list] = {
    "eiger": [1600.0, 1697.4],
    "pilatus": [1284.7, 1308.6],
}


OAV_CONFIG_FILES = {
    "zoom_params_file": "/dls_sw/i24/software/gda_versions/gda_9_34/config/xml/jCameraManZoomLevels.xml",
    "oav_config_json": "/dls_sw/i24/software/daq_configuration/json/OAVCentring.json",
    "display_config": "/dls_sw/i24/software/gda_versions/var/display.configuration",
}
OAV1_CAM = "http://bl24i-di-serv-01.diamond.ac.uk:8080/OAV1.mjpg.mjpg"

HEADER_FILES_PATH = Path("/dls_sw/i24/scripts/fastchips/").expanduser().resolve()

INTERNAL_FILES_PATH = Path(__file__).absolute().parent


def _params_file_location() -> Path:
    beamline: str | None = environ.get("BEAMLINE")
    filepath: Path

    if beamline:
        filepath = _read_visit_directory_from_file() / "tmp/serial/parameters"
    else:
        filepath = INTERNAL_FILES_PATH

    filepath.mkdir(parents=True, exist_ok=True)

    return filepath


PARAM_FILE_NAME = "parameters.json"
# Paths for rw - these should have been created on startup
PARAM_FILE_PATH = _params_file_location()
PARAM_FILE_PATH_FT = PARAM_FILE_PATH / "fixed_target"
LITEMAP_PATH = PARAM_FILE_PATH_FT / "litemaps"
# Paths for r only
PVAR_FILE_PATH = INTERNAL_FILES_PATH / "fixed_target/pvar_files"
CS_FILES_PATH = INTERNAL_FILES_PATH / "fixed_target/cs"
