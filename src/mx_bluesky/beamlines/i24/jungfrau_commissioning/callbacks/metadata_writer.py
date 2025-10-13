import json

from bluesky.callbacks import CallbackBase
from dodal.devices.i24.commissioning_jungfrau import JunfrauCommissioningWriter

from mx_bluesky.beamlines.i24.parameters.constants import PlanNameConstants
from mx_bluesky.common.external_interaction.ispyb.ispyb_store import IspybIds
from mx_bluesky.common.parameters.rotation import SingleRotationScan
from mx_bluesky.common.utils.log import LOGGER

READING_DUMP_FILENAME = "collection_info.json"


class JsonMetadataWriter(CallbackBase):
    """Callback class to handle the creation of metadata json files for commissioning.

    To use, subscribe the Bluesky RunEngine to an instance of this class.
    E.g.:
        metadata_writer_callback = JsonMetadataWriter(parameters)
        RE.subscribe(metadata_writer_callback)
    Or decorate a plan using bluesky.preprocessors.subs_decorator.

    See: https://blueskyproject.io/bluesky/callbacks.html#ways-to-invoke-callbacks

    """

    def __init__(self, writer: JunfrauCommissioningWriter):
        self.writer = writer
        self.beam_xy = None
        self.wavelength_in_a = None
        self.energy_in_kev = None
        self.detector_distance_mm = None
        self.descriptors: dict[str, dict] = {}
        self.flux: float | None = None
        self.transmission: float | None = None
        self.parameters: SingleRotationScan | None = None

        super().__init__()

    def start(self, doc: dict):  # type: ignore
        if doc.get("subplan_name") == PlanNameConstants.ROTATION_META_READ:
            json_params = doc.get("rotation_scan_params")
            assert json_params is not None
            LOGGER.info(
                f"Metadata writer recieved start document with experiment parameters {json_params}"
            )
            self.parameters = SingleRotationScan(**json.loads(json_params))
            self.run_start_uid = doc.get("uid")
            self.dcid = doc.get("dcid")

    def descriptor(self, doc: dict):  # type: ignore
        self.descriptors[doc["uid"]] = doc

    def event(self, doc: dict):  # type: ignore
        event_descriptor = self.descriptors[doc["descriptor"]]

        if event_descriptor.get("name") == PlanNameConstants.ROTATION_META_READ:
            assert self.parameters is not None
            data = doc.get("data")
            assert data is not None
            self.wavelength_in_a = data.get("dcm-wavelength_in_a")
            self.energy_in_kev = data.get("dcm-energy_in_kev")
            self.detector_distance_mm = data.get("detector_motion-z")

            if self.detector_distance_mm:
                self.beam_xy = self.parameters.detector_params.get_beam_position_mm(
                    self.detector_distance_mm
                )

            LOGGER.info(
                f"Metadata writer received parameters, transmission: {self.transmission}, flux: {self.flux}, wavelength: {self.wavelength_in_a}, det distance: {self.detector_distance_mm}, beam_xy: {self.beam_xy}"
            )

    def stop(self, doc: dict):  # type: ignore
        assert self.parameters is not None
        if (
            self.run_start_uid is not None
            and doc.get("run_start") == self.run_start_uid
        ):
            self.writer.final_path.parent.mkdir(exist_ok=True)
            with open(
                self.writer.final_path.parent / READING_DUMP_FILENAME,
                "w",
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "wavelength_in_a": self.wavelength_in_a,
                            "energy_kev": self.energy_in_kev,
                            "angular_increment_deg": self.parameters.rotation_increment_deg,
                            # "beam_xy_mm": self.beam_xy,
                            "detector_distance_mm": self.detector_distance_mm,
                            "dcid": self.dcid.data_collection_ids[0]
                        }
                    )
                )
