from __future__ import annotations

from typing import TYPE_CHECKING

from mx_bluesky.common.external_interaction.callbacks.common.logging_callback import (
    format_doc_for_log,
)
from mx_bluesky.common.external_interaction.callbacks.common.plan_reactive_callback import (
    PlanReactiveCallback,
)
from mx_bluesky.common.external_interaction.nexus.nexus_utils import (
    AxisDirection,
    create_beam_and_attenuator_parameters,
    vds_type_based_on_bit_depth,
)
from mx_bluesky.common.external_interaction.nexus.write_nexus import NexusWriter
from mx_bluesky.common.utils.log import NEXUS_LOGGER
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.rotation import SingleRotationScan

if TYPE_CHECKING:
    from event_model.documents import Event, EventDescriptor, RunStart


class RotationNexusFileCallback(PlanReactiveCallback):
    """Callback class to handle the creation of Nexus files based on experiment
    parameters for rotation scans

    To use, subscribe the Bluesky RunEngine to an instance of this class.
    E.g.:
        nexus_file_handler_callback = NexusFileCallback(parameters)
        RE.subscribe(nexus_file_handler_callback)
    Or decorate a plan using bluesky.preprocessors.subs_decorator.

    See: https://blueskyproject.io/bluesky/callbacks.html#ways-to-invoke-callbacks
    """

    def __init__(self) -> None:
        super().__init__(NEXUS_LOGGER)
        self.run_uid: str | None = None
        self.writer: NexusWriter | None = None
        self.descriptors: dict[str, EventDescriptor] = {}
        # used when multiple collections are made in one detector arming event:
        self.full_num_of_images: int | None = None
        self.meta_data_run_number: int | None = None

    def activity_gated_descriptor(self, doc: EventDescriptor):
        self.descriptors[doc["uid"]] = doc

    def activity_gated_event(self, doc: Event):
        event_descriptor = self.descriptors.get(doc["descriptor"])
        if event_descriptor is None:
            NEXUS_LOGGER.warning(
                f"Rotation Nexus handler {self} received event doc {format_doc_for_log(doc)} and "
                "has no corresponding descriptor record"
            )
            return doc
        if event_descriptor.get("name") == CONST.DESCRIPTORS.HARDWARE_READ_DURING:
            NEXUS_LOGGER.info(
                f"Nexus handler received event from read hardware {format_doc_for_log(doc)}"
            )
            data = doc["data"]
            assert self.writer, "Nexus writer not initialised"
            (
                self.writer.beam,
                self.writer.attenuator,
            ) = create_beam_and_attenuator_parameters(
                data["dcm-energy_in_kev"],
                data["flux-flux_reading"],
                data["attenuator-actual_transmission"],
            )
            vds_data_type = vds_type_based_on_bit_depth(doc["data"]["eiger_bit_depth"])
            self.writer.create_nexus_file(vds_data_type)
            NEXUS_LOGGER.info(f"Nexus file created at {self.writer.data_filename}")
        return doc

    def activity_gated_start(self, doc: RunStart):
        if doc.get("subplan_name") == CONST.PLAN.ROTATION_MULTI:
            self.full_num_of_images = doc.get("full_num_of_images")
            self.meta_data_run_number = doc.get("meta_data_run_number")
        if doc.get("subplan_name") == CONST.PLAN.ROTATION_OUTER:
            self.run_uid = doc.get("uid")
            hyperion_params = doc.get("mx_bluesky_parameters")
            assert isinstance(hyperion_params, str)
            NEXUS_LOGGER.info(
                f"Nexus writer received start document with experiment parameters {hyperion_params}"
            )
            parameters = SingleRotationScan.model_validate_json(hyperion_params)
            NEXUS_LOGGER.info("Setting up nexus file...")

            det_size = (
                parameters.detector_params.detector_size_constants.det_size_pixels
            )
            shape = (parameters.num_images, det_size.width, det_size.height)
            self.writer = NexusWriter(
                parameters,
                shape,
                parameters.scan_points,
                omega_start_deg=parameters.omega_start_deg,
                chi_start_deg=parameters.chi_start_deg or 0,
                phi_start_deg=parameters.phi_start_deg or 0,
                vds_start_index=parameters.nexus_vds_start_img,
                full_num_of_images=self.full_num_of_images,
                meta_data_run_number=self.meta_data_run_number,
                axis_direction=AxisDirection.NEGATIVE
                if parameters.features.omega_flip
                else AxisDirection.POSITIVE,
            )
