from mx_bluesky.hyperion.external_interaction.callbacks.beamline.i03 import (
    setup_callbacks,
)


def test_setup_callbacks():
    current_number_of_callbacks = 8
    cbs = setup_callbacks()
    assert len(cbs) == current_number_of_callbacks
    assert len(set(cbs)) == current_number_of_callbacks
