import datetime
import json
import logging
import math
import os
import re
import subprocess
import warnings
from functools import lru_cache

import requests

from mx_bluesky.beamlines.i24.serial.parameters import SSXType
from mx_bluesky.beamlines.i24.serial.setup_beamline import (
    Detector,
    Eiger,
    Pilatus,
    caget,
    cagetstring,
    pv,
)

try:
    from typing import Literal
except ImportError:
    pass

logger = logging.getLogger("I24ssx.DCID")


# Collection start/end script to kick off analysis
COLLECTION_START_SCRIPT = "/dls_sw/i24/scripts/RunAtStartOfCollect-i24-ssx.sh"
COLLECTION_END_SCRIPT = "/dls_sw/i24/scripts/RunAtEndOfCollect-i24-ssx.sh"

DEFAULT_ISPYB_SERVER = "https://ssx-dcserver.diamond.ac.uk"

CREDENTIALS_LOCATION = "/scratch/ssx_dcserver.key"


@lru_cache(maxsize=1)
def get_auth_header() -> dict:
    """Read the credentials file and build the Authorisation header"""
    if not os.path.isfile(CREDENTIALS_LOCATION):
        logger.warning(
            "Could not read %s; attempting to proceed without credentials",
            CREDENTIALS_LOCATION,
        )
        return {}
    with open(CREDENTIALS_LOCATION) as f:
        token = f.read().strip()
    return {"Authorization": "Bearer " + token}


class DCID:
    """
    Interfaces with ISPyB to allow ssx DCID/synchweb interaction.

    Args:
        server: The URL for the bridge server, if not the default.
        emit_errors:
            If False, errors while interacting with the DCID server will
            not be propagated to the caller. This decides if you want to
            stop collection if you can't get a DCID
        timeout: Length of time to wait for the DB server before giving up
        ssx_type: The type of SSX experiment this is for
        detector: The detector in use for current collection.


    Attributes:
        error:
            If an error has occured. This will be set, even if emit_errors = True
    """

    def __init__(
        self,
        *,
        server: str | None = None,
        emit_errors: bool = True,
        timeout: float = 10,
        ssx_type: SSXType = SSXType.FIXED,
        detector: Detector | Literal["eiger", "pilatus"] | None = None,
    ):
        self.detector: Detector
        # Handle case of string literal
        if detector == "eiger":
            self.detector = Eiger()
        elif detector == "pilatus":
            self.detector = Pilatus()
        elif detector is None:
            self.detector = Pilatus()
            warnings.warn(
                "Please pass detector= to DCID. Pilatus assumed, this will be removed in the future.",
                UserWarning,
                stacklevel=5,
            )

        self.server = server or DEFAULT_ISPYB_SERVER
        self.emit_errors = emit_errors
        self.error = False
        self.timeout = timeout
        self.ssx_type = SSXType(ssx_type)
        self.dcid = None

    def generate_dcid(
        self,
        visit: str,
        image_dir: str,
        num_images: int,
        exposure_time: float,
        start_time: datetime.datetime | None = None,
        shots_per_position: int = 1,
        pump_exposure_time: float | None = None,
        pump_delay: float = 0,
        pump_status: int = 0,
    ):
        """Generate an ispyb DCID.

        Args:
            visit: The name of the visit e.g. "mx12345-4"
            image_dir: The location the images will be written
        """
        try:
            if not start_time:
                start_time = datetime.datetime.now().astimezone()
            elif not start_time.timetz:
                start_time = start_time.astimezone()

            # Gather data from the beamline
            detector_distance = float(caget(self.detector.pv.detector_distance))
            wavelength = float(caget(self.detector.pv.wavelength))
            resolution = get_resolution(self.detector, detector_distance, wavelength)
            beamsize_x, beamsize_y = get_beamsize()
            transmission = float(caget(self.detector.pv.transmission)) * 100
            xbeam, ybeam = get_beam_center(self.detector)

            if isinstance(self.detector, Pilatus):
                # Mirror the construction that the PPU does
                fileTemplate = get_pilatus_filename_template_from_pvs()
                startImageNumber = 0
            elif isinstance(self.detector, Eiger):
                # Eiger base filename is directly written to the PV
                # Nexgen then uses this to write the .nxs file
                fileTemplate = str(cagetstring(self.detector.pv.file_name)) + ".nxs"
                startImageNumber = 1
            else:
                raise ValueError("Unknown detector:", self.detector)

            events = [
                {
                    "name": "Xray probe",
                    "offset": 0,
                    "duration": exposure_time,
                    "period": exposure_time,
                    "repetition": shots_per_position,
                    "eventType": "XrayDetection",
                }
            ]
            if pump_status > 0:
                # https://confluence.diamond.ac.uk/pages/viewpage.action?pageId=131238829
                # https://confluence.diamond.ac.uk/display/MXTech/Dynamics+and+fixed+targets
                # pump_status = 0: no pump probe
                # pump_status = 1: pump then probe
                # pump_status = 2: pump within probe
                # pump_status = 3-7: different EAVA modes (i.e. also pump then probe)
                if pump_status != 2 and self.ssx_type is SSXType.FIXED:
                    # Pump status could be 1 for extruder but not have this.
                    # pump then probe - pump_delay corresponds to time *before* first image
                    pump_delay = -pump_delay
                events.append(
                    {
                        "name": "Laser probe",
                        "offset": pump_delay,
                        "duration": pump_exposure_time,
                        # "period": None,
                        "repetition": 1,
                        "eventType": "LaserExcitation",
                    },
                )

            data = {
                "detectorDistance": float(detector_distance),
                "detectorId": self.detector.id,
                "exposureTime": float(exposure_time),
                "fileTemplate": fileTemplate,
                "imageDirectory": str(image_dir),
                "numberOfImages": int(num_images),
                "resolution": float(resolution),
                "startImageNumber": startImageNumber,
                "startTime": start_time.isoformat(),
                "transmission": float(transmission),
                "visit": visit,
                "wavelength": float(wavelength),
                "group": {"experimentType": self.ssx_type.value},
                "xBeam": xbeam,
                "yBeam": ybeam,
                "ssx": {
                    "eventChain": {
                        "events": events,
                    }
                },
            }
            if beamsize_x and beamsize_y:
                data["beamSizeAtSampleX"] = beamsize_x / 1000
                data["beamSizeAtSampleY"] = beamsize_y / 1000

            # Log what we are doing here
            try:
                logger.info(
                    "BRIDGE: POST /dc --data %s",
                    repr(json.dumps(data)),
                )
            except Exception:
                logger.info(
                    "Caught exception converting data to JSON. Data:\n%s\nVERBOSE:\n%s",
                    str({k: type(v) for k, v in data.items()}),
                )
                raise

            resp = requests.post(
                f"{self.server}/dc",
                json=data,
                timeout=self.timeout,
                headers=get_auth_header(),
            )
            resp.raise_for_status()
            self.dcid = resp.json()["dataCollectionId"]
            logger.info("Generated DCID %s", self.dcid)
        except requests.HTTPError as e:
            self.error = True
            logger.error(
                "DCID generation Failed; Reason from server: %s", e.response.text
            )
            if self.emit_errors:
                raise
            logger.exception("Error generating DCID: %s", e)
        except Exception as e:
            self.error = True
            if self.emit_errors:
                raise
            logger.exception("Error generating DCID: %s", e)

    def __int__(self):
        return self.dcid

    def notify_start(self):
        """Send notifications that the collection is now starting"""
        if self.dcid is None:
            return None
        try:
            command = [COLLECTION_START_SCRIPT, str(self.dcid)]
            logger.info("Running %s", " ".join(command))
            subprocess.Popen(command)
        except Exception as e:
            self.error = True
            if self.emit_errors:
                raise
            logger.warning("Error starting start of collect script: %s", e)

    def notify_end(self):
        """Send notifications that the collection has now ended"""
        if self.dcid is None:
            return
        try:
            command = [COLLECTION_END_SCRIPT, str(self.dcid)]
            logger.info("Running %s", " ".join(command))
            subprocess.Popen(command)
        except Exception as e:
            self.error = True
            if self.emit_errors:
                raise
            logger.warning("Error running end of collect notification: %s", e)

    def collection_complete(
        self, end_time: str | datetime.datetime | None = None, aborted: bool = False
    ) -> None:
        """
        Mark an ispyb DCID as completed.

        Args:
            dcid: The Collection ID to mark as finished
            end_time: The predetermined end time
            aborted: Was this collection aborted?
        """
        try:
            # end_time might be a string from time.ctime
            if isinstance(end_time, str):
                end_time = datetime.datetime.strptime(end_time, "%a %b %d %H:%M:%S %Y")
                logger.debug("Parsed end time: %s", end_time)

            if not end_time:
                end_time = datetime.datetime.now().astimezone()
            if not end_time.tzinfo:
                end_time = end_time.astimezone()

            status = (
                "DataCollection Cancelled" if aborted else "DataCollection Successful"
            )
            data = {
                "endTime": end_time.isoformat(),
                "runStatus": status,
            }
            if self.dcid is None:
                # Print what we would have sent. This means that if something is failing,
                # we still have the data to upload in the log files.
                logger.info(
                    'BRIDGE: No DCID but Would PATCH "/dc/XXXX" --data=%s',
                    repr(json.dumps(data)),
                )
                return

            logger.info(
                'BRIDGE: PATCH "/dc/%s" --data=%s', self.dcid, repr(json.dumps(data))
            )
            response = requests.patch(
                f"{self.server}/dc/{self.dcid}",
                json=data,
                timeout=self.timeout,
                headers=get_auth_header(),
            )
            response.raise_for_status()
            logger.info("Successfully updated end time for DCID %d", self.dcid)
        except Exception as e:
            resp_obj = getattr(e, "response", None)
            try:
                if resp_obj is not None:
                    resp_str = resp_obj.text
                # resp_str = repr(getattr(e, "Iresponse", "<no attribute>"))
                else:
                    resp_str = "Resp object is None"
            except Exception:
                resp_str = f"<failed to determine {resp_obj!r}>"

            self.error = True
            if self.emit_errors:
                raise
            logger.warning("Error completing DCID: %s (%s)", e, resp_str)


def get_pilatus_filename_template_from_pvs() -> str:
    """
    Get the template file path by querying the detector PVs.

    Returns: A template string, with the image numbers replaced with '#'
    """

    filename = cagetstring(pv.pilat_filename)
    filename_template = cagetstring(pv.pilat_filetemplate)
    file_number = int(caget(pv.pilat_filenumber))
    # Exploit fact that passing negative numbers will put the - before the 0's
    expected_filename = str(filename_template % (filename, f"{file_number:05d}_", -9))
    # Now, find the -09 part of this
    numberpart = re.search(r"(-0+9)", expected_filename)
    # Make sure this was the only one
    if numberpart is not None:
        assert re.search(r"(-0+9)", expected_filename[numberpart.end() :]) is None
        template_fill = "#" * len(numberpart.group(0))
        return (
            expected_filename[: numberpart.start()]
            + template_fill
            + expected_filename[numberpart.end() :]
        )
    else:
        raise ValueError(f"{filename=} did not contain the numbers for templating")


def get_beamsize() -> tuple[float | None, float | None]:
    """
    Read the PVs to get the current beamsize.

    Returns:
        A tuple (x, y) of beam size (in µm). These values can be 'None'
        if the focus mode was unrecognised.
    """
    # These I24 modes are from GDA
    focus_modes = {
        "focus10": ("7x7", 7, 7),
        "focus20d": ("20x20", 20, 20),
        "focus30d": ("30x30", 30, 30),
        "focus50d": ("50x50", 50, 50),
        "focus1050d": ("10x50", 10, 50),
        "focus5010d": ("50x10", 50, 10),
        "focus3010d": ("30x10", 30, 10),
    }
    v_mode = caget("BL24I-OP-MFM-01:G0:TARGETAPPLY")
    h_mode = caget("BL24I-OP-MFM-01:G1:TARGETAPPLY")
    # Validate these and note an error otherwise
    if not v_mode.startswith("VMFM") or v_mode[4:] not in focus_modes:
        logger.error("Unrecognised vertical beam mode %s", v_mode)
    if not h_mode.startswith("HMFM") or h_mode[4:] not in focus_modes:
        logger.error("Unrecognised horizontal beam mode %s", h_mode)
    _, h, _ = focus_modes.get(h_mode[4:], (None, None, None))
    _, _, v = focus_modes.get(v_mode[4:], (None, None, None))

    return (h, v)


def get_resolution(detector: Detector, distance: float, wavelength: float) -> float:
    """
    Calculate the inscribed resolution for detector.

    This assumes perfectly centered beam as I don't know where to
    extract the beam position parameters yet.

    Args:
        distance: Distance to detector (mm)
        wavelength: Beam wavelength (Å)

    Returns:
        Maximum resolution (Å)
    """
    width = detector.image_size_mm[0]
    return round(wavelength / (2 * math.sin(math.atan(width / (2 * distance)) / 2)), 2)


def get_beam_center(detector: Detector) -> tuple[float, float]:
    """Get the detector beam center, in mm"""
    beamX = float(caget(detector.pv.beamx)) * detector.pixel_size_mm[0]
    beamY = float(caget(detector.pv.beamy)) * detector.pixel_size_mm[1]
    return (beamX, beamY)
