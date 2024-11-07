import datetime
import json
import math
import os
import re
import subprocess
from functools import lru_cache

import bluesky.plan_stubs as bps
import requests
from dodal.devices.i24.beam_center import DetectorBeamCenter
from dodal.devices.i24.dcm import DCM
from dodal.devices.i24.focus_mirrors import FocusMirrorsMode

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import PumpProbeSetting
from mx_bluesky.beamlines.i24.serial.log import SSX_LOGGER
from mx_bluesky.beamlines.i24.serial.parameters import (
    BeamSettings,
    ExtruderParameters,
    FixedTargetParameters,
    SSXType,
)
from mx_bluesky.beamlines.i24.serial.setup_beamline import (
    Detector,
    Eiger,
    Pilatus,
    caget,
    cagetstring,
    pv,
)

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
    detector_name: str,
):
    # In the future this should also read the transmission from the attenuator, but no
    # device yet. See https://github.com/DiamondLightSource/dodal/issues/889
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
        expt_parameters: Collection parameters input by user.


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
        self.ssx_type = ssx_type
        self.dcid = None

    def generate_dcid(
        self,
        beam_settings: BeamSettings,
        image_dir: str,
        num_images: int,
        shots_per_position: int = 1,
        start_time: datetime.datetime | None = None,
        pump_probe: bool = False,
    ):
        """Generate an ispyb DCID.

        Args:
            wavelength (float): Wavelength read from dcm, in A.
            image_dir(str): The location the images will be written.
            num_images (int): Total number of images to be collected.
            start_time (datetime): Start time of collection.
            shots_per_position (int): Number of exposures per position in a chip. \
                Defaults to 1, which works for extruder.
            pump_probe (bool): It True, pump probe collection. Defaults to False.
        """
        try:
            if not start_time:
                start_time = datetime.datetime.now().astimezone()
            elif not start_time.timetz:
                start_time = start_time.astimezone()

            # Gather data from the beamline
            resolution = get_resolution(
                self.detector,
                self.parameters.detector_distance_mm,
                beam_settings.wavelength_in_a,
            )
            beamsize_x, beamsize_y = beam_settings.beam_size_in_um
            transmission = self.parameters.transmission * 100
            xbeam, ybeam = beam_settings.beam_center_in_mm

            # TODO This is already done in other bits of code, why redo, just grab it
            if isinstance(self.detector, Pilatus):
                # Mirror the construction that the PPU does
                fileTemplate = get_pilatus_filename_template_from_pvs()
                startImageNumber = 0
            elif isinstance(self.detector, Eiger):
                # Eiger base filename is directly written to the PV
                # Nexgen then uses this to write the .nxs file
                fileTemplate = self.parameters.filename + ".nxs"
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
                if self.ssx_type is SSXType.FIXED:
                    # pump then probe - pump_delay corresponds to time *before* first image
                    pump_delay = (
                        -self.parameters.laser_delay_s  # type: ignore
                        if self.parameters.pump_repeat is not PumpProbeSetting.Short2  # type: ignore
                        else self.parameters.laser_delay_s
                    )  # type: ignore
                else:
                    pump_delay = self.parameters.laser_delay_s  # type: ignore
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
                "fileTemplate": fileTemplate,
                "imageDirectory": image_dir,
                "numberOfImages": num_images,
                "resolution": resolution,
                "startImageNumber": startImageNumber,
                "startTime": start_time.isoformat(),
                "transmission": transmission,
                "visit": self.parameters.visit.name,
                "wavelength": beam_settings.wavelength_in_a,
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
