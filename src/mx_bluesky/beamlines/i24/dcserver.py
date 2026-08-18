"""Client for ssx-dcserver, the REST service i24 deposits ISPyB data collections to.

I24 does not write to ISPyB directly the way the hyperion-style plans do; it POSTs to
this bridge instead. Both the serial collection plans and the jungfrau commissioning
ones go through it, so the address, the credentials and the endpoints live here rather
than under serial/, which is where they started.
"""

from __future__ import annotations

import json
import logging
import math
import os
from typing import Any

import requests

from mx_bluesky.common.utils.log import LOGGER

# Its own logger, rather than either of the ones its callers use: the serial handlers
# are attached to SSX_LOGGER and do not propagate, so serial.log routes this one to the
# collection log as well (see its config()), while everything else reaches it here.
DCSERVER_LOGGER = logging.getLogger("I24dcserver")
DCSERVER_LOGGER.parent = LOGGER

DEFAULT_DCSERVER_URL = "https://ssx-dcserver.diamond.ac.uk"
CREDENTIALS_LOCATION = "/scratch/ssx_dcserver.key"

# So a test can be pointed at a development deployment, or given a token that is not
# the beamline's, without editing code or being able to write to /scratch.
SERVER_ENV_VAR = "SSX_DCSERVER_URL"
TOKEN_ENV_VAR = "SSX_DCSERVER_TOKEN"

DEFAULT_TIMEOUT_S = 10


class DCServerError(Exception):
    """The dcserver would not accept a request."""


def _raise_for_status(response: requests.Response) -> None:
    """Raise with what the server said, not just which status it said it with.

    A bare status tells you nothing about which field it objected to, and the schema
    rejects anything it does not recognise, so the body is the part worth reading.
    """
    try:
        response.raise_for_status()
    except requests.HTTPError as e:
        raise DCServerError(f"{e}. The server said: {response.text}") from e


def get_dcserver_url() -> str:
    """Which dcserver to talk to: $SSX_DCSERVER_URL if set, else the production one."""
    return os.environ.get(SERVER_ENV_VAR) or DEFAULT_DCSERVER_URL


def get_auth_header() -> dict[str, str]:
    """Build the Authorisation header, from $SSX_DCSERVER_TOKEN or the key file.

    Deliberately not cached: the environment variables exist so that a test can move
    between servers, and a token cached from the first call would outlive the server it
    authenticates against.
    """
    token = os.environ.get(TOKEN_ENV_VAR)
    if not token:
        if not os.path.isfile(CREDENTIALS_LOCATION):
            DCSERVER_LOGGER.warning(
                "Could not read %s; attempting to proceed without credentials",
                CREDENTIALS_LOCATION,
            )
            return {}
        with open(CREDENTIALS_LOCATION) as f:
            token = f.read().strip()
    return {"Authorization": "Bearer " + token}


def resolution_at_detector_edge(
    width_mm: float, distance: float, wavelength: float
) -> float:
    """The inscribed resolution, in Å, for a detector of this width, in mm."""
    return round(
        wavelength / (2 * math.sin(math.atan(width_mm / (2 * distance)) / 2)), 2
    )


def create_data_collection(
    data: dict[str, Any], timeout: float = DEFAULT_TIMEOUT_S
) -> int:
    """Create an ISPyB data collection, returning its DCID.

    The server rejects fields it does not know about, so `data` must only hold keys from
    its DataCollectionIn schema; detectorId, fileTemplate, imageDirectory, startTime,
    visit and group are required.
    """
    DCSERVER_LOGGER.info('BRIDGE: POST "/dc" --data=%s', repr(json.dumps(data)))
    response = requests.post(
        f"{get_dcserver_url()}/dc",
        json=data,
        timeout=timeout,
        headers=get_auth_header(),
    )
    _raise_for_status(response)
    return response.json()["dataCollectionId"]


def update_data_collection(
    dcid: int, data: dict[str, Any], timeout: float = DEFAULT_TIMEOUT_S
) -> None:
    """Update an existing ISPyB data collection, e.g. to mark it finished."""
    DCSERVER_LOGGER.info(
        'BRIDGE: PATCH "/dc/%s" --data=%s', dcid, repr(json.dumps(data))
    )
    response = requests.patch(
        f"{get_dcserver_url()}/dc/{dcid}",
        json=data,
        timeout=timeout,
        headers=get_auth_header(),
    )
    _raise_for_status(response)
