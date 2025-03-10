from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from mx_bluesky.common.external_interaction.callbacks.common.plan_reactive_callback import (
    PlanReactiveCallback,
)
from mx_bluesky.common.external_interaction.nexus.nexus_utils import (
    create_beam_and_attenuator_parameters,
    vds_type_based_on_bit_depth,
)
from mx_bluesky.common.external_interaction.nexus.write_nexus import NexusWriter
from mx_bluesky.common.parameters.constants import DocDescriptorNames, PlanNameConstants
from mx_bluesky.common.parameters.gridscan import (
    SpecifiedThreeDGridScan,
)
from mx_bluesky.common.utils.log import NEXUS_LOGGER

if TYPE_CHECKING:
    from event_model.documents import Event, EventDescriptor, RunStart

T = TypeVar("T", bound="SpecifiedThreeDGridScan")


class GridscanNexusFileCallback(PlanReactiveCallback):
    """Callback class to handle the creation of Nexus files based on experiment \
    parameters. Initialises on recieving a 'start' document for the \
    'run_gridscan_move_and_tidy' sub plan, which must also contain the run parameters, \
    as metadata under the 'hyperion_internal_parameters' key. Actually writes the \
    nexus files on updates the timestamps on recieving the 'ispyb_reading_hardware' event \
    document, and finalises the files on getting a 'stop' document for the whole run.

    To use, subscribe the Bluesky RunEngine to an instance of this class.
    E.g.:
        nexus_file_handler_callback = NexusFileCallback(parameters)
        RE.subscribe(nexus_file_handler_callback)
    Or decorate a plan using bluesky.preprocessors.subs_decorator.

    See: https://blueskyproject.io/bluesky/callbacks.html#ways-to-invoke-callbacks
    """

    def __init__(self, param_type: type[T]) -> None:
        super().__init__(NEXUS_LOGGER)
        self.param_type = param_type
        self.run_start_uid: str | None = None
        self.nexus_writer_1: NexusWriter | None = None
        self.nexus_writer_2: NexusWriter | None = None
        self.descriptors: dict[str, EventDescriptor] = {}
        self.log = NEXUS_LOGGER

    def activity_gated_start(self, doc: RunStart):
        if doc.get("subplan_name") == PlanNameConstants.GRIDSCAN_OUTER:
            mx_bluesky_parameters = doc.get("mx_bluesky_parameters")
            assert isinstance(mx_bluesky_parameters, str)
            NEXUS_LOGGER.info(
                f"Nexus writer received start document with experiment parameters {mx_bluesky_parameters}"
            )
            parameters = self.param_type.model_validate_json(mx_bluesky_parameters)
            d_size = parameters.detector_params.detector_size_constants.det_size_pixels
            grid_n_img_1 = parameters.scan_indices[1]
            grid_n_img_2 = parameters.num_images - grid_n_img_1
            data_shape_1 = (grid_n_img_1, d_size.width, d_size.height)
            data_shape_2 = (grid_n_img_2, d_size.width, d_size.height)
            run_number_2 = parameters.detector_params.run_number + 1
            self.nexus_writer_1 = NexusWriter(
                parameters, data_shape_1, parameters.scan_points_first_grid
            )
            self.nexus_writer_2 = NexusWriter(
                parameters,
                data_shape_2,
                parameters.scan_points_second_grid,
                run_number=run_number_2,
                vds_start_index=parameters.scan_indices[1],
                omega_start_deg=90,
            )
            self.run_start_uid = doc.get("uid")

    def activity_gated_descriptor(self, doc: EventDescriptor):
        self.descriptors[doc["uid"]] = doc

    def activity_gated_event(self, doc: Event) -> Event | None:
        event_descriptor = self.descriptors.get(doc["descriptor"])
        assert event_descriptor is not None
        if event_descriptor.get("name") == DocDescriptorNames.HARDWARE_READ_DURING:
            data = doc["data"]
            for nexus_writer in [self.nexus_writer_1, self.nexus_writer_2]:
                assert nexus_writer, "Nexus callback did not receive start doc"
                (
                    nexus_writer.beam,
                    nexus_writer.attenuator,
                ) = create_beam_and_attenuator_parameters(
                    data["dcm-energy_in_kev"],
                    data["flux-flux_reading"],
                    data["attenuator-actual_transmission"],
                )
                vds_data_type = vds_type_based_on_bit_depth(
                    doc["data"]["eiger_bit_depth"]
                )
                nexus_writer.create_nexus_file(vds_data_type)
                NEXUS_LOGGER.info(f"Nexus file created at {nexus_writer.data_filename}")

        return super().activity_gated_event(doc)
