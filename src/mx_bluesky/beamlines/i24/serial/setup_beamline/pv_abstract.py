"""
Cleaner abstractions of the PV table.

Takes the PV tables from I24's setup_beamline and wraps a slightly more
abstract wrapper around them.
"""

from mx_bluesky.beamlines.i24.serial.setup_beamline import pv


class Eiger:
    id = 94
    name = "eiger"

    pixel_size_mm = (0.075, 0.075)
    image_size_pixels = (3108, 3262)

    image_size_mm = tuple(
        round(a * b, 3) for a, b in zip(image_size_pixels, pixel_size_mm, strict=False)
    )

    det_y_threshold = 70.0
    det_y_target = 59.0

    class PV:
        detector_distance = pv.eiger_detdist
        wavelength = pv.eiger_wavelength
        transmission = "BL24I-EA-PILAT-01:cam1:FilterTransm"
        filename_rbv = pv.eiger_od_filename_rbv
        file_name = pv.eiger_od_filename
        file_path = pv.eiger_od_filepath
        file_template = None
        sequence_id = pv.eiger_seq_id
        beamx = pv.eiger_beamx
        beamy = pv.eiger_beamy
        bit_depth = pv.eiger_bitdepthrbv

    def __str__(self) -> str:
        return self.name


Detector = Eiger
