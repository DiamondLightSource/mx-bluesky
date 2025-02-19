import datetime
import json
import math
import os
import subprocess
from functools import lru_cache

import bluesky.plan_stubs as bps
import requests
from dodal.beamlines import i24
from dodal.devices.i24.beam_center import DetectorBeamCenter
from dodal.devices.i24.dcm import DCM
from dodal.devices.i24.focus_mirrors import FocusMirrorsMode
from dodal.devices.i24.pilatus_metadata import PilatusMetadata

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import PumpProbeSetting
from mx_bluesky.beamlines.i24.serial.log import SSX_LOGGER
from mx_bluesky.beamlines.i24.serial.parameters import (
    BeamSettings,
    DetectorName,
    ExtruderParameters,
    FixedTargetParameters,
)
from mx_bluesky.beamlines.i24.serial.setup_beamline import Detector, Eiger, Pilatus

# Collection start/end script to kick off analysis
COLLECTION_START_SCRIPT = "/dls_sw/i24/scripts/RunAtStartOfCollect-i24-ssx.sh"
COLLECTION_END_SCRIPT = "/dls_sw/i24/scripts/RunAtEndOfCollect-i24-ssx.sh"

DEFAULT_ISPYB_SERVER = "https://ssx-dcserver.diamond.ac.uk"

CREDENTIALS_LOCATION = "/scratch/ssx_dcserver.key"


@lru_cache(maxsize=1)
def get_auth_header() -> dict:
    """Read the credentials file and build the Authorisation header"""
    if not os.path.isfile(CREDENTIALS_LOCATION):
        SSX_LOGGER.warning(
            "Could not read %s; attempting to proceed without credentials",
            CREDENTIALS_LOCATION,
        )
        return {}
    with open(CREDENTIALS_LOCATION) as f:
        token = f.read().strip()
    return {"Authorization": "Bearer " + token}


def read_beam_info_from_hardware(
    dcm: DCM,
    mirrors: FocusMirrorsMode,
    beam_center: DetectorBeamCenter,
    detector_name: DetectorName,
):
    """ Read the beam information from hardware.

    Args:
        dcm (DCM): The decm device.
        mirrors (FocusMirrorMode): The device describing the focus mirror mode settings.
        beam_center (DetectorBeamCenter): A device to set and read the beam center on \
            the detector.
        detector_name (DetectorName): The detector currently in use.

    Returns:
        BeamSettings parameter model.
    """
    wavelength = yield from bps.rd(dcm.wavelength_in_a)
    beamsize_x = yield from bps.rd(mirrors.beam_size_x)
    beamsize_y = yield from bps.rd(mirrors.beam_size_y)
    pixel_size = (
        Eiger().pixel_size_mm if detector_name == "eiger" else Pilatus().pixel_size_mm
    )
    beam_center_x = yield from bps.rd(beam_center.beam_x)
    beam_center_y = yield from bps.rd(beam_center.beam_y)
    return BeamSettings(
        wavelength_in_a=wavelength,
        beam_size_in_um=(beamsize_x, beamsize_y),
        beam_center_in_mm=(
            beam_center_x * pixel_size[0],
            beam_center_y * pixel_size[1],
        ),
    )


class DCID:
    """ Interfaces with ISPyB to allow ssx DCID/synchweb interaction.

    Args:
        server (str, optional): The URL for the bridge server, if not the default.
        emit_errors (bool, optional): If False, errors while interacting with the DCID \
            server will not be propagated to the caller. This decides if you want to \
            stop collection if you can't get a DCID. Defaults to True.
        timeout (float, optional): Length of time in s to wait for the DB server before \
            giving up. Defaults to 10 s.
        expt_parameters (ExtruderParameters | FixedTargetParameters): Collection \
            parameters input by user.


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
        expt_params: ExtruderParameters | FixedTargetParameters,
    ):
        self.parameters = expt_params
        self.detector: Detector
        # Handle case of string literal
        match expt_params.detector_name:
            case "eiger":
                self.detector = Eiger()
            case "pilatus":
                self.detector = Pilatus()

        self.server = server or DEFAULT_ISPYB_SERVER
        self.emit_errors = emit_errors
        self.error = False
        self.timeout = timeout
        self.dcid = None

    def generate_dcid(
        self,
        beam_settings: BeamSettings,
        image_dir: str,
        file_template: str,
        num_images: int,
        shots_per_position: int = 1,
        start_time: datetime.datetime | None = None,
        pump_probe: bool = False,
    ):
        """Generate an ispyb DCID.

        Args:
            beam_settings (BeamSettings): Information about the beam read from hardware.
            image_dir (str): The location the images will be written to.
            num_images (int): Total number of images to be collected.
            shots_per_position (int, optional): Number of exposures per position in a \
                chip. Defaults to 1, which works for extruder.
            start_time(datetime, optional): Collection start time. Defaults to None.
            pump_probe (bool, optional): If True, a pump probe collection is running. \
                Defaults to False.
        """
        try:
            if not start_time:
                start_time = datetime.datetime.now().astimezone()
            elif not start_time.timetz:
                start_time = start_time.astimezone()

            resolution = get_resolution(
                self.detector,
                self.parameters.detector_distance_mm,
                beam_settings.wavelength_in_a,
            )
            beamsize_x, beamsize_y = beam_settings.beam_size_in_um
            transmission = self.parameters.transmission * 100
            xbeam, ybeam = beam_settings.beam_center_in_mm

            if isinstance(self.detector, Pilatus):
                startImageNumber = 0
            elif isinstance(self.detector, Eiger):
                startImageNumber = 1
            else:
                raise ValueError("Unknown detector:", self.detector)

            events = [
                {
                    "name": "Xray probe",
                    "offset": 0,
                    "duration": self.parameters.exposure_time_s,
                    "period": self.parameters.exposure_time_s,
                    "repetition": shots_per_position,
                    "eventType": "XrayDetection",
                }
            ]
            if pump_probe:
                match self.parameters:
                    case FixedTargetParameters():
                        # pump then probe - pump_delay corresponds to time *before* first image
                        pump_delay = (
                            -self.parameters.laser_delay_s
                            if self.parameters.pump_repeat
                            is not PumpProbeSetting.Short2
                            else self.parameters.laser_delay_s
                        )
                    case ExtruderParameters():
                        pump_delay = self.parameters.laser_delay_s
                events.append(
                    {
                        "name": "Laser probe",
                        "offset": pump_delay,
                        "duration": self.parameters.laser_dwell_s,
                        "repetition": 1,
                        "eventType": "LaserExcitation",
                    },
                )

            data = {
                "detectorDistance": self.parameters.detector_distance_mm,
                "detectorId": self.detector.id,
                "exposureTime": self.parameters.exposure_time_s,
                "fileTemplate": file_template,
                "imageDirectory": image_dir,
                "numberOfImages": num_images,
                "resolution": resolution,
                "startImageNumber": startImageNumber,
                "startTime": start_time.isoformat(),
                "transmission": transmission,
                "visit": self.parameters.visit.name,
                "wavelength": beam_settings.wavelength_in_a,
                "group": {
                    "experimentType": self.parameters.ispyb_experiment_type.value
                },
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
                SSX_LOGGER.info(
                    "BRIDGE: POST /dc --data %s",
                    repr(json.dumps(data)),
                )
            except Exception:
                SSX_LOGGER.info(
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
            SSX_LOGGER.info("Generated DCID %s", self.dcid)
        except requests.HTTPError as e:
            self.error = True
            SSX_LOGGER.error(
                "DCID generation Failed; Reason from server: %s", e.response.text
            )
            if self.emit_errors:
                raise
            SSX_LOGGER.exception("Error generating DCID: %s", e)
        except Exception as e:
            self.error = True
            if self.emit_errors:
                raise
            SSX_LOGGER.exception("Error generating DCID: %s", e)

    def __int__(self):
        return self.dcid

    def notify_start(self):
        """Send notifications that the collection is now starting"""
        if self.dcid is None:
            return None
        try:
            command = [COLLECTION_START_SCRIPT, str(self.dcid)]
            SSX_LOGGER.info("Running %s", " ".join(command))
            subprocess.Popen(command)
        except Exception as e:
            self.error = True
            if self.emit_errors:
                raise
            SSX_LOGGER.warning("Error starting start of collect script: %s", e)

    def notify_end(self):
        """Send notifications that the collection has now ended"""
        if self.dcid is None:
            return
        try:
            command = [COLLECTION_END_SCRIPT, str(self.dcid)]
            SSX_LOGGER.info("Running %s", " ".join(command))
            subprocess.Popen(command)
        except Exception as e:
            self.error = True
            if self.emit_errors:
                raise
            SSX_LOGGER.warning("Error running end of collect notification: %s", e)

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
                SSX_LOGGER.debug("Parsed end time: %s", end_time)

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
                SSX_LOGGER.info(
                    'BRIDGE: No DCID but Would PATCH "/dc/XXXX" --data=%s',
                    repr(json.dumps(data)),
                )
                return

            SSX_LOGGER.info(
                'BRIDGE: PATCH "/dc/%s" --data=%s', self.dcid, repr(json.dumps(data))
            )
            response = requests.patch(
                f"{self.server}/dc/{self.dcid}",
                json=data,
                timeout=self.timeout,
                headers=get_auth_header(),
            )
            response.raise_for_status()
            SSX_LOGGER.info("Successfully updated end time for DCID %d", self.dcid)
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
            SSX_LOGGER.warning("Error completing DCID: %s (%s)", e, resp_str)


def get_pilatus_filename_template_from_device():
    """
    Get the template file path by querying the detector PVs, mirror the construction \
    that the PPU does.

    Returns:
        A template string, with the image numbers replaced with '#'
    """
    pilatus_metadata: PilatusMetadata = i24.pilatus_metadata()

    filename_template = yield from bps.rd(pilatus_metadata.filename_template)
    return filename_template


def get_resolution(detector: Detector, distance: float, wavelength: float) -> float:
    """ Calculate the inscribed resolution for detector.

    This assumes perfectly centered beam as I don't know where to extract the beam \
    position parameters yet.

    Args:
        detector (Detector): Detector instance, Eiger() or Pilatus().
        distance (float): Distance to detector, in mm.
        wavelength (float): Beam wavelength, in Å.

    Returns:
        Maximum resolution, in Å.
    """
    width = detector.image_size_mm[0]
    return round(wavelength / (2 * math.sin(math.atan(width / (2 * distance)) / 2)), 2)
