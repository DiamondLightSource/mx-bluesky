from __future__ import annotations

import json
from pathlib import Path

from bluesky.callbacks import CallbackBase
from nexgen.nxs_utils import Attenuator, Axis, Beam, Detector, Goniometer, Source
from nexgen.nxs_utils.Detector import JungfrauDetector
from scanspec.core import Path as ScanPath
from scanspec.specs import Line

from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.log import LOGGER
from mx_bluesky.beamlines.i24.jungfrau_commissioning.utils.params import (
    RotationScanParameters,
)


def create_detector_parameters(params: RotationScanParameters) -> Detector:
    """Returns the detector information in a format that nexgen wants.

    Args:
        detector_params (DetectorParams): The detector params as Artemis stores them.

    Returns:
        Detector: Detector description for nexgen.
    """
    jf_params = JungfrauDetector(
        "Jungfrau 1M",
        (1066, 1030),
        "Si",
        1000000,
        -10,
    )

    detector_axes = [
        Axis(
            "det_z",
            ".",
            "translation",
            (0.0, 0.0, 1.0),
            105,
        )
    ]
    # Eiger parameters, axes, beam_center, exp_time, [fast, slow]
    return Detector(
        jf_params,
        detector_axes,
        [0, 0],  # Beam centre TODO
        params.exposure_time_s,
        [(-1.0, 0.0, 0.0), (0.0, -1.0, 0.0)],
    )


def create_I24_VGonio_axes(
    params: RotationScanParameters,
    scan_points: dict,
):
    gonio_axes = [
        Axis("omega", ".", "rotation", (0.0, 1.0, 0.0), params.omega_start_deg),
        Axis(
            name="sam_z",
            depends="omega",
            transformation_type="translation",
            vector=(0.0, 0.0, 1.0),
            start_pos=params.z,
        ),
        Axis(
            name="sam_y",
            depends="sam_z",
            transformation_type="translation",
            vector=(0.0, 1.0, 0.0),
            start_pos=params.y,
        ),
        Axis(
            name="sam_x",
            depends="sam_y",
            transformation_type="translation",
            vector=(1.0, 0.0, 0.0),
            start_pos=params.x,
        ),
    ]
    return Goniometer(gonio_axes, scan_points)


class JFRotationNexusWriter(NexusWriter):
    def __init__(
        self,
        parameters: RotationScanParameters,
        wavelength: float,
        flux: float,
        transmission: float,
    ) -> None:
        self.detector = create_detector_parameters(parameters)
        self.beam, self.attenuator = (
            Beam(wavelength, flux),
            Attenuator(transmission),
        )
        self.source = Source("I24")
        self.directory = Path(parameters.storage_directory)
        self.filename = parameters.nexus_filename
        self.start_index = 0
        self.full_num_of_images = parameters.get_num_images()
        self.nexus_file = self.directory / f"{parameters.nexus_filename}.nxs"
        self.master_file = self.directory / f"{parameters.nexus_filename}_master.h5"

        scan_spec = Line(
            axis="omega",
            start=parameters.omega_start_deg,
            stop=(parameters.scan_width_deg + parameters.omega_start_deg),
            num=parameters.get_num_images(),
        )
        scan_path = ScanPath(scan_spec.calculate())
        self.scan_points: dict = scan_path.consume().midpoints
        self.goniometer = create_I24_VGonio_axes(parameters, self.scan_points)

    def _get_data_shape_for_vds(self) -> tuple[int, ...]:
        nexus_detector_params: JungfrauDetector = self.detector.detector_params
        return (self.full_num_of_images, *nexus_detector_params.image_size)


class NexusFileHandlerCallback(CallbackBase):
    """Callback class to handle the creation of Nexus files based on experiment \
    parameters. Initialises on recieving a 'start' document for the \
    'rotation_scan_with_cleanup' sub plan, which must also contain the run parameters, \
    as metadata under the 'rotation_scan_params' key.

    To use, subscribe the Bluesky RunEngine to an instance of this class.
    E.g.:
        nexus_file_handler_callback = NexusFileHandlerCallback(parameters)
        RE.subscribe(nexus_file_handler_callback)
    Or decorate a plan using bluesky.preprocessors.subs_decorator.

    See: https://blueskyproject.io/bluesky/callbacks.html#ways-to-invoke-callbacks

    """

    nexus_writer: JFRotationNexusWriter
    descriptors: dict[str, dict] = {}
    parameters: RotationScanParameters
    wavelength: float | None = None
    flux: float | None = None
    transmission: float | None = None

    def start(self, doc: dict):
        if doc.get("subplan_name") == "rotation_scan_with_cleanup":
            LOGGER.info(
                "Nexus writer recieved start document with experiment parameters."
            )
            json_params = doc.get("rotation_scan_params")
            assert json_params is not None
            self.parameters = RotationScanParameters(**json.loads(json_params))
            self.run_start_uid = doc.get("uid")

    def descriptor(self, doc: dict):
        self.descriptors[doc["uid"]] = doc

    def event(self, doc: dict):
        LOGGER.info("Nexus handler received event document.")
        event_descriptor = self.descriptors[doc["descriptor"]]

        if event_descriptor.get("name") == "gonio xyz":
            assert self.parameters is not None
            data: dict | None = doc.get("data")
            assert data is not None
            self.parameters.x = data.get("vgonio_x")
            self.parameters.y = data.get("vgonio_yh")
            self.parameters.z = data.get("vgonio_z")
            LOGGER.info(
                f"Nexus handler received x, y, z: {self.parameters.x ,self.parameters.y ,self.parameters.z}."  # noqa
            )
        if event_descriptor.get("name") == "beam params":
            assert self.parameters is not None
            data = doc.get("data")
            assert data is not None
            self.transmission = data.get("beam_params_transmission")
            self.flux = data.get("beam_params_intensity")
            self.flux_xbpm2 = data.get("beam_params_flux_xbpm2")
            self.flux_xbpm3 = data.get("beam_params_flux_xbpm3")
            self.wavelength = data.get("beam_params_wavelength")
            LOGGER.info(
                f"Nexus handler received beam parameters, transmission: {self.transmission}, flux: {self.flux}, wavelength: {self.wavelength}."  # noqa
            )

    def stop(self, doc: dict):
        if (
            self.run_start_uid is not None
            and doc.get("run_start") == self.run_start_uid
        ):
            # assert self.parameters.x is not None
            # assert self.parameters.y is not None
            # assert self.parameters.z is not None
            # assert self.transmission is not None
            # assert self.flux is not None
            # assert self.wavelength is not None
            # LOGGER.info("writing nexus file")
            # nexus_writer = JFRotationNexusWriter(
            #     self.parameters, self.wavelength, self.flux, self.transmission
            # )
            # nexus_writer.create_nexus_file()
            with open(
                Path(self.parameters.storage_directory) / "collection_info.json", "w"
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "intensity": self.flux,
                            "flux_xbpm2": self.flux_xbpm2,
                            "flux_xbpm3": self.flux_xbpm3,
                            "wavelength": self.wavelength,
                            "x": self.parameters.x,
                            "y": self.parameters.y,
                            "z": self.parameters.z,
                        }
                    )
                )
