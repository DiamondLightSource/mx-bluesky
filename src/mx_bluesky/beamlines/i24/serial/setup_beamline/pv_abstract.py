"""
Cleaner abstractions of the PV table.

Takes the PV tables from I24's setup_beamline and wraps a slightly more
abstract wrapper around them.
"""

from mx_bluesky.beamlines.i24.serial.setup_beamline import pv


class Pilatus:
    id = 58
    name = "pilatus"

    # fast, slow / width, height
    image_size_pixels = (2463, 2527)
    pixel_size_mm = (0.172, 0.172)
    image_size_mm = tuple(
        round(a * b, 3) for a, b in zip(image_size_pixels, pixel_size_mm, strict=False)
    )

    det_y_threshold = 640.0
    det_y_target = 647.0

    class pv:
        detector_distance = pv.pilat_detdist
        wavelength = pv.pilat_wavelength
        transmission = pv.pilat_filtertrasm
        file_name = pv.pilat_filename
        file_path = pv.pilat_filepath
        file_template = pv.pilat_filetemplate
        file_number = pv.pilat_filenumber
        beamx = pv.pilat_beamx
        beamy = pv.pilat_beamy

    def __str__(self) -> str:
        return self.name


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

    class pv:
        detector_distance = pv.eiger_detdist
        wavelength = pv.eiger_wavelength
        transmission = "BL24I-EA-PILAT-01:cam1:FilterTransm"
        filenameRBV = pv.eiger_ODfilenameRBV
        file_name = pv.eiger_ODfilename
        file_path = pv.eiger_ODfilepath
        file_template = None
        sequence_id = pv.eiger_seqID
        beamx = pv.eiger_beamx
        beamy = pv.eiger_beamy
        bit_depth = pv.eiger_bitdepthrbv

    def __str__(self) -> str:
        return self.name


Detector = Pilatus | Eiger
