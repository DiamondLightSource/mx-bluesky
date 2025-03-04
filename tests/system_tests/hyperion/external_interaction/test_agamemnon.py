from deepdiff.diff import DeepDiff

from mx_bluesky.hyperion.external_interaction.agamemnon import (
    AGAMEMNON_URL,
    AgamemnonLoadCentreCollect,
    SinglePin,
    _get_parameters_from_url,
    get_pin_type_from_agamemnon_parameters,
    populate_parameters_from_agamemnon,
)

EXPECTED_PARAMETERS = AgamemnonLoadCentreCollect(
    visit="cm00000-0", detector_distance_mm=180.8
)


def test_given_test_agamemnon_instruction_then_returns_none_loop_type():
    params = _get_parameters_from_url(AGAMEMNON_URL + "/example/collect")
    loop_type = get_pin_type_from_agamemnon_parameters(params)
    assert loop_type == SinglePin()


def test_given_test_agamemnon_instruction_then_load_centre_collect_parameters_populated():
    params = _get_parameters_from_url(AGAMEMNON_URL + "/example/collect")
    load_centre_collect = populate_parameters_from_agamemnon(params)
    difference = DeepDiff(
        load_centre_collect,
        EXPECTED_PARAMETERS,
    )
    assert not difference
