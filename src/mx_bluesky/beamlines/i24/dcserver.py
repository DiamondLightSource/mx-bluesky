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


class DCServerError(requests.HTTPError):
    """The dcserver would not accept a request.

    An HTTPError, carrying the response, so that callers which catch HTTPError or read
    `e.response.text` see no difference from calling requests themselves.
    """


def _raise_for_status(response: requests.Response) -> None:
    """Raise with what the server said, not just which status it said it with.

    A bare status tells you nothing about which field it objected to, and the schema
    rejects anything it does not recognise, so the body is the part worth reading.
    """
    try:
        response.raise_for_status()
    except requests.HTTPError as e:
        raise DCServerError(
            f"{e}. The server said: {response.text}", response=response
        ) from e


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


def _log_request(method: str, path: str, data: dict[str, Any]) -> None:
    """Log the request as JSON, so a failed one can be replayed from the log by hand."""
    try:
        DCSERVER_LOGGER.info(
            'BRIDGE: %s "%s" --data=%s', method, path, repr(json.dumps(data))
        )
    except (TypeError, ValueError):
        DCSERVER_LOGGER.error(
            "Could not convert %s %s data to JSON; field types: %s",
            method,
            path,
            {k: type(v) for k, v in data.items()},
        )
        raise


def create_data_collection(
    data: dict[str, Any],
    *,
    server: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    autosample: bool = False,
) -> int:
    """Create an ISPyB data collection, returning its DCID.

    The server rejects fields it does not know about, so `data` must only hold keys from
    its DataCollectionIn schema; detectorId, fileTemplate, imageDirectory, startTime,
    visit and group are required.

    Args:
        data: The DataCollectionIn body.
        server: The dcserver to use, if not get_dcserver_url().
        timeout: Request timeout, in seconds.
        autosample: Ask the server to derive a sample for the collection when the data
            does not name one. Best effort: deriving none is not an error.
    """
    _log_request("POST", "/dc", data)
    response = requests.post(
        f"{server or get_dcserver_url()}/dc",
        params={"autosample": "true"} if autosample else None,
        json=data,
        timeout=timeout,
        headers=get_auth_header(),
    )
    _raise_for_status(response)
    return response.json()["dataCollectionId"]


def update_data_collection(
    dcid: int,
    data: dict[str, Any],
    *,
    server: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> None:
    """Update an existing ISPyB data collection, e.g. to mark it finished.

    Args:
        dcid: The data collection to update.
        data: The fields to change.
        server: The dcserver to use, if not get_dcserver_url().
        timeout: Request timeout, in seconds.
    """
    _log_request("PATCH", f"/dc/{dcid}", data)
    response = requests.patch(
        f"{server or get_dcserver_url()}/dc/{dcid}",
        json=data,
        timeout=timeout,
        headers=get_auth_header(),
    )
    _raise_for_status(response)
