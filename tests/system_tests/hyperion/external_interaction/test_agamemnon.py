import warnings

from deepdiff.diff import DeepDiff
from pydantic_extra_types.semantic_version import SemanticVersion

from mx_bluesky.common.parameters.components import (
    PARAMETER_VERSION,
    TopNByMaxCountSelection,
)
from mx_bluesky.hyperion.external_interaction.agamemnon import (
    AGAMEMNON_URL,
    AgamemnonLoadCentreCollect,
    SinglePin,
    _get_parameters_from_url,
    get_pin_type_from_agamemnon_parameters,
    populate_parameters_from_agamemnon,
)

EXPECTED_PARAMETERS = AgamemnonLoadCentreCollect(
    visit="cm00000-0",
    detector_distance_mm=180.8,
    sample_id=12345,
    sample_puck=1,
    sample_pin=1,
    parameter_model_version=SemanticVersion.validate_from_str(str(PARAMETER_VERSION)),
    select_centres=TopNByMaxCountSelection(n=1),
)


def test_given_test_agamemnon_instruction_then_returns_none_loop_type():
    params = _get_parameters_from_url(AGAMEMNON_URL + "/example/collect")
    loop_type = get_pin_type_from_agamemnon_parameters(params)
    assert loop_type == SinglePin()


def test_given_test_agamemnon_instruction_then_load_centre_collect_parameters_populated():
    params = _get_parameters_from_url(AGAMEMNON_URL + "/example/collect")
    load_centre_collect = populate_parameters_from_agamemnon(params)
    difference = True
    with warnings.catch_warnings():
        # Suppress warning exceptions due to Pydantic 2.11 deprecation warnings
        warnings.filterwarnings(
            "ignore", "Accessing this attribute on the instance is deprecated"
        )
        difference = DeepDiff(
            load_centre_collect,
            EXPECTED_PARAMETERS,
        )
    assert not difference
