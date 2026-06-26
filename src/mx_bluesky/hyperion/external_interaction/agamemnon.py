import json
import os
import re
import time
from collections.abc import Sequence
from enum import StrEnum
from os import path
from typing import Any, TypeVar

import requests
from dodal.utils import get_beamline_name
from pydantic import BaseModel
from requests import ConnectionError, HTTPError, Response, Timeout

from mx_bluesky.common.external_interaction.alerting import get_alerting_service
from mx_bluesky.common.parameters.components import (
    WithVisit,
)
from mx_bluesky.common.parameters.constants import (
    GridscanParamConstants,
)
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.utils.utils import convert_angstrom_to_ev
from mx_bluesky.hyperion._plan_runner_params import Wait
from mx_bluesky.hyperion.blueapi.parameters import (
    LoadCentreCollectParams,
    MultiSamplePinTypeParam,
    PinTypeParam,
    SingleSamplePinTypeParam,
)
from mx_bluesky.hyperion.plan_runner import PlanError
from mx_bluesky.hyperion.external_interaction.config_server import (
    get_hyperion_feature_settings,
)

T = TypeVar("T", bound=WithVisit)
MULTIPIN_PREFIX = "multipin"
MULTIPIN_FORMAT_DESC = "Expected multipin format is multipin_{number_of_wells}x{well_size}+{distance_between_tip_and_first_well}"
MULTIPIN_REGEX = rf"^{MULTIPIN_PREFIX}_(\d+)x(\d+(?:\.\d+)?)\+(\d+(?:\.\d+)?)$"
MX_GENERAL_ROOT_REGEX = r"^/dls/(?P<beamline>[^/]+)/data/[^/]*/(?P<visit>[^/]+)(?:/|$)"

MAX_TRIES = 3
RETRY_INITIAL_DELAY_S = 2


class _InstructionType(StrEnum):
    WAIT = "wait"
    COLLECT = "collect"


def create_parameters_from_agamemnon() -> Sequence[BaseModel]:
    """Fetch the next instruction from agamemnon and convert it into one or more
    mx-bluesky instructions.
    Returns:
        The generated sequence of mx-bluesky parameters, or empty list if
        no instructions.
    Raises:
        PlanError: if the instructions could not be fetched from Agamemnon
    """
    beamline_name = get_beamline_name("i03")
    agamemnon_instruction = _get_next_instruction(beamline_name)
    if agamemnon_instruction:
        match _instruction_and_data(agamemnon_instruction):
            case (_InstructionType.COLLECT, data):
                return _populate_parameters_from_agamemnon(data)
            case (_InstructionType.WAIT, data):
                return [
                    Wait.model_validate(
                        {
                            "duration_s": data,
                        }
                    )
                ]

    return []


def _instruction_and_data(agamemnon_instruction: dict) -> tuple[str, Any]:
    instruction, data = next(iter(agamemnon_instruction.items()))
    if instruction not in _InstructionType.__members__.values():
        raise KeyError(
            f"Unexpected instruction from agamemnon: {agamemnon_instruction}"
        )
    return instruction, data


def _get_parameters_from_url(url: str) -> dict:
    tries, delay = MAX_TRIES, RETRY_INITIAL_DELAY_S
    while tries > 0:
        tries -= 1
        try:
            response = requests.get(url, headers={"Accept": "application/json"})
            try:
                response.raise_for_status()
                break
            except HTTPError as e:
                if _is_server_error(response):
                    LOGGER.warning(
                        f"Agamemnon returned server error status {response.status_code}, retries left {tries}: {str(e)}"
                    )
                else:
                    msg = f"Agamemnon returned unexpected HTTP response status code {response.status_code}"
                    get_alerting_service().raise_error_alert(msg, {})
                    raise PlanError(msg) from e
        except ConnectionError as e:
            LOGGER.warning(
                f"Connection error attempting to connect to agamemnon, retries left {tries}",
                exc_info=e,
            )
        except Timeout:
            LOGGER.warning(
                f"Timed out attempting to connect to agamemnon, retries left {tries}"
            )
        if tries:
            time.sleep(delay)  # noqa
            delay *= 2
    else:
        msg = f"Unable to fetch instruction from agamemnon after {MAX_TRIES} attempts, ending UDC."
        get_alerting_service().raise_error_alert(msg, {})
        raise PlanError(msg)
    return json.loads(response.content)


def _is_server_error(response: Response):
    return 500 <= response.status_code < 600


def _get_pin_type_from_agamemnon_collect_parameters(
    collect_parameters: dict,
) -> PinTypeParam:
    loop_type_name: str | None = collect_parameters["sample"]["loopType"]
    if loop_type_name:
        regex_search = re.search(MULTIPIN_REGEX, loop_type_name)
        if regex_search:
            wells, well_size, tip_to_first_well = regex_search.groups()
            return MultiSamplePinTypeParam(
                wells=int(wells),
                well_size_um=float(well_size),
                tip_to_first_well_um=float(tip_to_first_well),
            )
        else:
            loop_type_message = (
                f"Agamemnon loop type of {loop_type_name} not recognised"
            )
            if loop_type_name.startswith(MULTIPIN_PREFIX):
                raise ValueError(f"{loop_type_message}. {MULTIPIN_FORMAT_DESC}")
            LOGGER.warning(f"{loop_type_message}, assuming single pin")
    return SingleSamplePinTypeParam()


def _get_next_instruction(beamline: str) -> dict:
    return _get_parameters_from_url(get_agamemnon_url() + f"getnextcollect/{beamline}")


def get_agamemnon_url() -> str:
    return os.environ.get("AGAMEMNON_URL", "http://agamemnon.diamond.ac.uk/")


def _get_withvisit_parameters_from_agamemnon(parameters: dict) -> tuple:
    try:
        prefix = parameters["prefix"]
        collection = parameters["collection"]
        # Assuming distance is identical for multiple collections. Remove after https://github.com/DiamondLightSource/mx-bluesky/issues/773
        detector_distance = collection[0]["distance"]
    except KeyError as e:
        raise KeyError("Unexpected json from agamemnon") from e

    match = re.match(MX_GENERAL_ROOT_REGEX, prefix) if prefix else None

    if match:
        return (match.group("visit"), detector_distance)

    raise ValueError(
        f"Agamemnon prefix '{prefix}' does not match MX-General root structure"
    )


def _get_withenergy_parameters_from_agamemnon(parameters: dict) -> dict[str, Any]:
    try:
        first_collection: dict = parameters["collection"][0]
        wavelength: float | None = first_collection.get("wavelength")
        assert isinstance(wavelength, float)
        demand_energy_ev = convert_angstrom_to_ev(wavelength)
        return {"demand_energy_ev": demand_energy_ev}
    except (KeyError, IndexError, AttributeError, TypeError):
        return {"demand_energy_ev": None}


def _populate_parameters_from_agamemnon(
    agamemnon_params,
) -> Sequence[LoadCentreCollectParams]:
    if not agamemnon_params:
        # Empty dict means no instructions
        return []

    visit, detector_distance = _get_withvisit_parameters_from_agamemnon(
        agamemnon_params
    )
    with_energy_params = _get_withenergy_parameters_from_agamemnon(agamemnon_params)
    pin_type = _get_pin_type_from_agamemnon_collect_parameters(agamemnon_params)
    collections = agamemnon_params["collection"]
    visit_directory, file_name = path.split(agamemnon_params["prefix"])
    use_roi_mode = get_hyperion_feature_settings().XRC_USE_ROI_MODE
    return [
        LoadCentreCollectParams.model_validate(
            {
                "visit": visit,
                "detector_distance_mm": detector_distance,
                "sample_id": agamemnon_params["sample"]["id"],
                "sample_puck": agamemnon_params["sample"]["container"],
                "sample_pin": agamemnon_params["sample"]["position"],
                "select_centres": {
                    "name": "TopNByMaxCount",
                    "n": pin_type.wells,
                },
                **with_energy_params,
                "robot_load_then_centre": {
                    "storage_directory": str(visit_directory) + "/xraycentring",
                    "file_name": file_name,
                    "pin_type": pin_type,
                    "omega_starts_deg": [0.0, 90.0],
                    "chi_start_deg": collection["chi"],
                    "transmission_frac": 1.0,
                    "exposure_time_s": GridscanParamConstants.EXPOSURE_TIME_S,
                    "use_roi_mode": use_roi_mode,
                },
                "multi_rotation_scan": {
                    "comment": collection["comment"],
                    "storage_directory": str(visit_directory),
                    "exposure_time_s": collection["exposure_time"],
                    "file_name": file_name,
                    "transmission_frac": collection["transmission"],
                    "rotation_increment_deg": collection["omega_increment"],
                    "ispyb_experiment_type": collection["experiment_type"],
                    "snapshot_omegas_deg": [0.0, 90.0, 180.0, 270.0],
                    "rotation_scans": [
                        {
                            "scan_width_deg": (
                                collection["number_of_images"]
                                * collection["omega_increment"]
                            ),
                            "omega_start_deg": collection["omega_start"],
                            "phi_start_deg": collection["phi_start"],
                            "chi_start_deg": collection["chi"],
                            "rotation_direction": "Positive",
                        }
                    ],
                },
            }
        )
        for collection in collections
    ]
