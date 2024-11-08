import os
import pathlib
import pprint
import time
from typing import Literal

import requests

from mx_bluesky.beamlines.i24.serial.fixed_target.ft_utils import ChipType, MappingType
from mx_bluesky.beamlines.i24.serial.log import SSX_LOGGER
from mx_bluesky.beamlines.i24.serial.parameters import (
    ExtruderParameters,
    FixedTargetParameters,
)
from mx_bluesky.beamlines.i24.serial.setup_beamline import Eiger, caget


def call_nexgen(
    chip_prog_dict: dict | None,
    parameters: ExtruderParameters | FixedTargetParameters,
    wavelength: float,
    beam_center: list[float],
    expt_type: Literal["fixed-target", "extruder"] = "fixed-target",
):
    det_type = parameters.detector_name
    print(f"det_type: {det_type}")

    current_chip_map = None
    if expt_type == "fixed-target" and isinstance(parameters, FixedTargetParameters):
        if not (
            parameters.map_type == MappingType.NoMap
            or parameters.chip.chip_type == ChipType.Custom
        ):
            # NOTE Nexgen server is still on nexgen v0.7.2 (fully working for ssx)
            # Will need to be updated, for correctness sake map needs to be None.
            current_chip_map = "/dls_sw/i24/scripts/fastchips/litemaps/currentchip.map"
        pump_status = bool(parameters.pump_repeat)
        total_numb_imgs = parameters.total_num_images
    elif expt_type == "extruder" and isinstance(parameters, ExtruderParameters):
        # chip_prog_dict should be None for extruder (passed as input for now)
        total_numb_imgs = parameters.num_images
        pump_status = parameters.pump_status
    else:
        raise ValueError(f"{expt_type=} not recognised")

    filename_prefix = parameters.filename
    meta_h5 = parameters.visit / parameters.directory / f"{filename_prefix}_meta.h5"
    t0 = time.time()
    max_wait = 60  # seconds
    SSX_LOGGER.info(f"Watching for {meta_h5}")
    while time.time() - t0 < max_wait:
        if meta_h5.exists():
            SSX_LOGGER.info(f"Found {meta_h5} after {time.time() - t0:.1f} seconds")
            time.sleep(5)
            break
        SSX_LOGGER.debug(f"Waiting for {meta_h5}")
        time.sleep(1)
    if not meta_h5.exists():
        SSX_LOGGER.warning(f"Giving up waiting for {meta_h5} after {max_wait} seconds")
        return False

    transmission = parameters.transmission

    if det_type == Eiger.name:
        bit_depth = int(caget(Eiger.pv.bit_depth))
        SSX_LOGGER.debug(
            f"Call to nexgen server with the following chip definition: \n{chip_prog_dict}"
        )

        access_token = pathlib.Path("/scratch/ssx_nexgen.key").read_text().strip()
        url = "https://ssx-nexgen.diamond.ac.uk/ssx_eiger/write"
        headers = {"Authorization": f"Bearer {access_token}"}

        payload = {
            "beamline": "i24",
            "beam_center": beam_center,
            "chipmap": current_chip_map,
            "chip_info": chip_prog_dict,
            "det_dist": parameters.detector_distance_mm,
            "exp_time": parameters.exposure_time_s,
            "expt_type": expt_type,
            "filename": filename_prefix,
            "num_imgs": total_numb_imgs,
            "pump_status": pump_status,
            "pump_exp": parameters.laser_dwell_s,
            "pump_delay": parameters.laser_delay_s,
            "transmission": transmission,
            "visitpath": os.fspath(meta_h5.parent),
            "wavelength": wavelength,
            "bit_depth": bit_depth,
        }
        SSX_LOGGER.info(f"Sending POST request to {url} with payload:")
        SSX_LOGGER.info(pprint.pformat(payload))
        response = requests.post(url, headers=headers, json=payload)
        SSX_LOGGER.info(
            f"Response: {response.text} (status code: {response.status_code})"
        )
        # the following will raise an error if the request was unsuccessful
        return response.status_code == requests.codes.ok
    return False
