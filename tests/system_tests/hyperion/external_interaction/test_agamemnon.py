from mx_bluesky.hyperion.external_interaction.agamemnon import (
    AGAMEMNON_URL,
    _get_parameters_from_url,
    _get_pin_type_from_agamemnon_parameters,
    _single_pin,
)


def test_given_test_agamemnon_instruction_then_returns_none_loop_type():
    params = _get_parameters_from_url(AGAMEMNON_URL + "/example/collect")
    loop_type = _get_pin_type_from_agamemnon_parameters(params)
    assert loop_type == _single_pin()
