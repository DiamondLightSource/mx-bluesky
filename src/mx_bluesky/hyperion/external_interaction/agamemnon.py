import dataclasses
import json
import re
from os import path
from typing import Any, TypeVar

import requests
from deepdiff.diff import DeepDiff
from dodal.utils import get_beamline_name
from jsonschema import ValidationError
from pydantic_extra_types.semantic_version import SemanticVersion

from mx_bluesky.common.parameters.components import (
    PARAMETER_VERSION,
    MxBlueskyParameters,
    TopNByMaxCountSelection,
    WithCentreSelection,
    WithSample,
    WithVisit,
)
from mx_bluesky.common.parameters.constants import (
    GridscanParamConstants,
)
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.utils.utils import convert_angstrom_to_eV
from mx_bluesky.hyperion.external_interaction.config_server import HyperionFeatureFlags
from mx_bluesky.hyperion.parameters.components import WithHyperionUDCFeatures
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.parameters.robot_load import RobotLoadThenCentre
from mx_bluesky.hyperion.parameters.rotation import (
    MultiRotationScan,
)

T = TypeVar("T", bound=WithVisit)
AGAMEMNON_URL = "http://agamemnon.diamond.ac.uk/"
MULTIPIN_PREFIX = "multipin"
MULTIPIN_FORMAT_DESC = "Expected multipin format is multipin_{number_of_wells}x{well_size}+{distance_between_tip_and_first_well}"
MULTIPIN_REGEX = rf"^{MULTIPIN_PREFIX}_(\d+)x(\d+(?:\.\d+)?)\+(\d+(?:\.\d+)?)$"
MX_GENERAL_ROOT_REGEX = r"^/dls/(?P<beamline>[^/]+)/data/[^/]*/(?P<visit>[^/]+)(?:/|$)"


class AgamemnonLoadCentreCollect(
    MxBlueskyParameters,
    WithVisit,
    WithSample,
    WithCentreSelection,
    WithHyperionUDCFeatures,
):
    """Experiment parameters to compare against GDA populated LoadCentreCollect."""

    robot_load_then_centre: RobotLoadThenCentre
    multi_rotation_scan: MultiRotationScan


@dataclasses.dataclass
class PinType:
    expected_number_of_crystals: int
    single_well_width_um: float
    tip_to_first_well_um: float = 0

    @property
    def full_width(self) -> float:
        """This is the "width" of the area where there may be samples.

        From a pin perspective this is along the length of the pin but we use width here as
        we mount the sample at 90 deg to the optical camera.

        We calculate the full width by adding all the gaps between wells then assuming
        there is a buffer of {tip_to_first_well_um} either side too. In reality the
        calculation does not need to be very exact as long as we get a width that's good
        enough to use for optical centring and XRC grid size.
        """
        return (self.expected_number_of_crystals - 1) * self.single_well_width_um + (
            2 * self.tip_to_first_well_um
        )


class SinglePin(PinType):
    def __init__(self):
        super().__init__(1, GridscanParamConstants.WIDTH_UM)

    @property
    def full_width(self) -> float:
        return self.single_well_width_um


def _get_parameters_from_url(url: str) -> dict:
    response = requests.get(url, headers={"Accept": "application/json"})
    response.raise_for_status()
    response_json = json.loads(response.content)
    try:
        return response_json["collect"]
    except KeyError as e:
        raise KeyError(f"Unexpected json from agamemnon: {response_json}") from e


def get_pin_type_from_agamemnon_parameters(parameters: dict) -> PinType:
    loop_type_name: str | None = parameters["sample"]["loopType"]
    if loop_type_name:
        regex_search = re.search(MULTIPIN_REGEX, loop_type_name)
        if regex_search:
            wells, well_size, tip_to_first_well = regex_search.groups()
            return PinType(int(wells), float(well_size), float(tip_to_first_well))
        else:
            loop_type_message = (
                f"Agamemnon loop type of {loop_type_name} not recognised"
            )
            if loop_type_name.startswith(MULTIPIN_PREFIX):
                raise ValueError(f"{loop_type_message}. {MULTIPIN_FORMAT_DESC}")
            LOGGER.warning(f"{loop_type_message}, assuming single pin")
    return SinglePin()


def get_next_instruction(beamline: str) -> dict:
    return _get_parameters_from_url(AGAMEMNON_URL + f"getnextcollect/{beamline}")


def get_withvisit_parameters_from_agamemnon(parameters: dict) -> tuple:
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


def get_withsample_parameters_from_agamemnon(parameters: dict) -> dict[str, Any]:
    assert parameters.get("sample"), "instruction does not have a sample"
    return {
        "sample_id": parameters["sample"]["id"],
        "sample_puck": parameters["sample"]["container"],
        "sample_pin": parameters["sample"]["position"],
    }


def get_withenergy_parameters_from_agamemnon(parameters: dict) -> dict[str, Any]:
    try:
        first_collection: dict = parameters["collection"][0]
        wavelength = first_collection.get("wavelength")
        assert isinstance(wavelength, float)
        demand_energy_ev = convert_angstrom_to_eV(wavelength)
        return {"demand_energy_ev": demand_energy_ev}
    except (KeyError, IndexError, AttributeError, TypeError):
        return {"demand_energy_ev": None}


def get_param_version() -> SemanticVersion:
    return SemanticVersion.validate_from_str(str(PARAMETER_VERSION))


def create_robot_load_then_centre_params_from_agamemnon(
    parameters: dict,
) -> RobotLoadThenCentre:
    visit, detector_distance = get_withvisit_parameters_from_agamemnon(parameters)
    with_sample_params = get_withsample_parameters_from_agamemnon(parameters)
    with_energy_params = get_withenergy_parameters_from_agamemnon(parameters)
    pin_type = get_pin_type_from_agamemnon_parameters(parameters)
    visit_directory, file_name = path.split(parameters["prefix"])
    return RobotLoadThenCentre(
        parameter_model_version=get_param_version(),
        storage_directory=visit_directory + "/xraycentring",
        visit=visit,
        detector_distance_mm=detector_distance,
        snapshot_directory=visit_directory + "/snapshots",
        omega_start_deg=0.0,
        chi_start_deg=0.0,
        transmission_frac=1.0,
        tip_offset_um=pin_type.full_width / 2,
        grid_width_um=pin_type.full_width,
        file_name=file_name,
        features=HyperionFeatureFlags(use_gpu_results=True),
        **with_energy_params,
        **with_sample_params,
    )


def create_rotation_params_from_agamemnon(
    parameters: dict,
) -> MultiRotationScan:
    visit, detector_distance = get_withvisit_parameters_from_agamemnon(parameters)
    with_sample_params = get_withsample_parameters_from_agamemnon(parameters)
    with_energy_params = get_withenergy_parameters_from_agamemnon(parameters)
    visit_directory, file_name = path.split(parameters["prefix"])

    first_collection = parameters["collection"][0]

    return MultiRotationScan.model_validate(
        {
            "parameter_model_version": get_param_version(),
            "comment": first_collection["comment"],
            "storage_directory": str(visit_directory),
            "detector_distance_mm": detector_distance,
            **with_energy_params,
            "exposure_time_s": first_collection["exposure_time"],
            "file_name": file_name,
            "sample_id": with_sample_params["sample_id"],
            "sample_puck": with_sample_params["sample_puck"],
            "sample_pin": with_sample_params["sample_pin"],
            "visit": visit,
            "transmission_frac": first_collection["transmission"],
            "rotation_increment_deg": first_collection["omega_increment"],
            "ispyb_experiment_type": first_collection["experiment_type"],
            "snapshot_omegas_deg": [0.0, 90.0, 180.0, 270.0],
            "rotation_scans": [
                {
                    "scan_width_deg": (
                        first_collection["number_of_images"]
                        * first_collection["omega_increment"]
                    ),
                    "omega_start_deg": first_collection["omega_start"],
                    "phi_start_deg": first_collection["phi_start"],
                    "chi_start_deg": first_collection["chi"],
                    "rotation_direction": "Positive",
                }
            ],
        }
    )


def populate_parameters_from_agamemnon(agamemnon_params):
    visit, detector_distance = get_withvisit_parameters_from_agamemnon(agamemnon_params)
    with_sample_params = get_withsample_parameters_from_agamemnon(agamemnon_params)
    pin_type = get_pin_type_from_agamemnon_parameters(agamemnon_params)
    robot_load_params = create_robot_load_then_centre_params_from_agamemnon(
        agamemnon_params
    )
    rotation_parameters = create_rotation_params_from_agamemnon(agamemnon_params)
    return AgamemnonLoadCentreCollect(
        parameter_model_version=SemanticVersion.validate_from_str(
            str(PARAMETER_VERSION)
        ),
        visit=visit,
        detector_distance_mm=detector_distance,
        select_centres=TopNByMaxCountSelection(n=pin_type.expected_number_of_crystals),
        robot_load_then_centre=robot_load_params,
        multi_rotation_scan=rotation_parameters,
        **with_sample_params,
    )


def create_parameters_from_agamemnon() -> AgamemnonLoadCentreCollect | None:
    beamline_name = get_beamline_name("i03")
    agamemnon_params = get_next_instruction(beamline_name)
    return (
        populate_parameters_from_agamemnon(agamemnon_params)
        if agamemnon_params
        else None
    )


def compare_params(load_centre_collect_params):
    try:
        parameters = create_parameters_from_agamemnon()

        # Log differences against GDA populated parameters
        differences = DeepDiff(
            parameters, load_centre_collect_params, math_epsilon=1e-5
        )
        if differences:
            LOGGER.info(
                f"Different parameters found when directly reading from Hyperion: {differences}"
            )
    except (ValueError, KeyError) as e:
        LOGGER.warning(f"Failed to compare parameters: {e}")
    except Exception as e:
        LOGGER.warning(f"Unexpected error occurred. Failed to compare parameters: {e}")


def update_params_from_agamemnon(parameters: T) -> T:
    try:
        beamline_name = get_beamline_name("i03")
        agamemnon_params = get_next_instruction(beamline_name)
        pin_type = get_pin_type_from_agamemnon_parameters(agamemnon_params)
        if isinstance(parameters, LoadCentreCollect):
            parameters.robot_load_then_centre.tip_offset_um = pin_type.full_width / 2
            parameters.robot_load_then_centre.grid_width_um = pin_type.full_width
            parameters.select_centres.n = pin_type.expected_number_of_crystals
            if pin_type != SinglePin():
                # Snapshots between each collection take a lot of time.
                # Before we do https://github.com/DiamondLightSource/mx-bluesky/issues/226
                # this will give no snapshots but that's preferable
                parameters.multi_rotation_scan.snapshot_omegas_deg = []
    except (ValueError, ValidationError) as e:
        LOGGER.warning(f"Failed to update parameters: {e}")
    except Exception as e:
        LOGGER.warning(f"Unexpected error occurred. Failed to update parameters: {e}")

    return parameters
