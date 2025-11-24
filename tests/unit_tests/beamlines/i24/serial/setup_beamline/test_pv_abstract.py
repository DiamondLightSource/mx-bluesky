from mx_bluesky.beamlines.i24.serial.setup_beamline import Eiger


def test_eiger():
    eig = Eiger()
    assert eig.image_size_mm == (233.1, 244.65)
