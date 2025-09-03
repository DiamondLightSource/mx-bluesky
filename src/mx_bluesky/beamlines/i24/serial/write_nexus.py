import os
import pathlib
import pprint
import time
from datetime import datetime

import bluesky.plan_stubs as bps
import requests

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import ChipType, MappingType
from mx_bluesky.beamlines.i24.serial.log import SSX_LOGGER
from mx_bluesky.beamlines.i24.serial.parameters import (
    ExtruderParameters,
    FixedTargetParameters,
)
from mx_bluesky.beamlines.i24.serial.setup_beamline import Eiger, caget, cagetstring


def call_nexgen(
    chip_prog_dict: dict | None,
    parameters: ExtruderParameters | FixedTargetParameters,
    wavelength_in_a: float,
    beam_center_in_pix: tuple[float, float],
    start_time: datetime,
):
    """Call the nexus writer by sending a request to nexgen-server.

    Args:
        chip_prog_dict (dict | None): Dictionary containing most of the information \
            passed to the program runner for the collection. Only used for fixed target.
        start_time
        parameters (SerialAndLaserExperiment): Collection parameters.
        wavelength_in_a (float): Wavelength, in A.
        beam_center_in_pix (list[float]): Beam center position on detector, in pixels.
        start_time (datetime): Collection start time.

    Raises:
        ValueError: For a wrong experiment type passed (either unknwon or not matched \
            to parameter model).

    """
    current_chip_map = None
    match parameters:
        case FixedTargetParameters():
            if not (
                parameters.map_type == MappingType.NoMap
                or parameters.chip.chip_type == ChipType.Custom
            ):
                # For nexgen >= 0.9.10
                current_chip_map = parameters.chip_map
            pump_status = bool(parameters.pump_repeat)
            total_numb_imgs = parameters.total_num_images
        case ExtruderParameters():
            total_numb_imgs = parameters.num_images
            pump_status = parameters.pump_status

    filename_prefix = cagetstring(Eiger.pv.filenameRBV)
    meta_h5 = parameters.visit / parameters.directory / f"{filename_prefix}_meta.h5"
    t0 = time.time()
    max_wait = 60  # seconds
    SSX_LOGGER.info(f"Watching for {meta_h5}")
    while time.time() - t0 < max_wait:
        if meta_h5.exists():
            SSX_LOGGER.info(f"Found {meta_h5} after {time.time() - t0:.1f} seconds")
            yield from bps.sleep(5)
            break
        SSX_LOGGER.debug(f"Waiting for {meta_h5}")
        yield from bps.sleep(1)
    if not meta_h5.exists():
        SSX_LOGGER.warning(f"Giving up waiting for {meta_h5} after {max_wait} seconds")
        return

    bit_depth = int(caget(Eiger.pv.bit_depth))
    SSX_LOGGER.debug(
        f"Call to nexgen server with the following chip definition: \n{chip_prog_dict}"
    )

    access_token = pathlib.Path("/scratch/ssx_nexgen.key").read_text().strip()
    url = "https://ssx-nexgen.diamond.ac.uk/ssx_eiger/write"
    headers = {"Authorization": f"Bearer {access_token}"}

    payload = {
        "beamline": "i24",
        "beam_center": beam_center_in_pix,
        "chipmap": current_chip_map,
        "chip_info": chip_prog_dict,
        "det_dist": parameters.detector_distance_mm,
        "exp_time": parameters.exposure_time_s,
        "expt_type": parameters.nexgen_experiment_type,
        "filename": filename_prefix,
        "num_imgs": total_numb_imgs,
        "pump_status": pump_status,
        "pump_exp": parameters.laser_dwell_s,
        "pump_delay": parameters.laser_delay_s,
        "transmission": parameters.transmission,
        "visitpath": os.fspath(meta_h5.parent),
        "wavelength": wavelength_in_a,
        "bit_depth": bit_depth,
        "start_time": start_time.isoformat(),
    }
    SSX_LOGGER.info(f"Sending POST request to {url} with payload:")
    SSX_LOGGER.info(pprint.pformat(payload))
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    SSX_LOGGER.info(f"Response: {response.text} (status code: {response.status_code})")
