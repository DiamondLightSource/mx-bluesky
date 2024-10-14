from mx_bluesky.beamlines.i24.serial.setup_beamline import Eiger, Pilatus


def test_eiger():
    eig = Eiger()
    assert eig.image_size_mm == (233.1, 244.65)


def test_pilatus():
    pil = Pilatus()
    assert pil.image_size_mm == (423.636, 434.644)
