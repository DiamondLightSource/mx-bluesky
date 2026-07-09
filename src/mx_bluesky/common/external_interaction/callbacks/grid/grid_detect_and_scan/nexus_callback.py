from __future__ import annotations

from typing import TYPE_CHECKING, Generic, TypeVar

from dodal.devices.detector import DetectorParams

from mx_bluesky.common.external_interaction.callbacks.common.plan_reactive_callback import (
    PlanReactiveCallback,
)
from mx_bluesky.common.external_interaction.nexus.nexus_utils import (
    create_beam_and_attenuator_parameters,
    vds_type_based_on_bit_depth,
)
from mx_bluesky.common.external_interaction.nexus.write_nexus import NexusWriter
from mx_bluesky.common.parameters.components import (
    DiffractionExperiment,
    DiffractionExperimentWithSample,
)
from mx_bluesky.common.parameters.constants import DocDescriptorNames, PlanNameConstants
from mx_bluesky.common.parameters.gridscan import (
    GridScanParams,
)
from mx_bluesky.common.utils.log import NEXUS_LOGGER

if TYPE_CHECKING:
    from event_model.documents import Event, EventDescriptor, RunStart

T = TypeVar("T", bound="DiffractionExperimentWithSample")


def _create_writers_from_params(
    params: DiffractionExperiment,
    detector_params: DetectorParams,
    grid_scan_params: GridScanParams,
) -> list[NexusWriter]:
    num_writers = grid_scan_params.num_grids
    writers = []
    d_size = detector_params.detector_size_constants.det_size_pixels
    for idx in range(num_writers):
        images_in_grid = len(grid_scan_params.scan_points[idx]["sam_x"])
        data_shape = (images_in_grid, d_size.width, d_size.height)
        run_number = detector_params.run_number + idx

        writers.append(
            NexusWriter(
                params,
                detector_params,
                data_shape,
                grid_scan_params.scan_points[idx],
                grid_scan_params.num_images,
                run_number=run_number,
                vds_start_index=grid_scan_params.scan_indices[idx],
                omega_start_deg=grid_scan_params.omega_starts_deg[idx],
            )
        )
    return writers


class GridscanNexusFileCallback(PlanReactiveCallback, Generic[T]):
    """Callback class to handle the creation of Nexus files based on experiment \
    parameters. Initialises on receiving a 'start' document for the \
    'run_gridscan_move_and_tidy' sub plan, which must also contain the run parameters, \
    as metadata under the 'mx_bluesky_parameters' key. Actually writes the \
    nexus files on updates the timestamps on receiving the 'ispyb_reading_hardware' event \
    document, and finalises the files on getting a 'stop' document for the whole run.

    To use, subscribe the Bluesky RunEngine to an instance of this class.
    E.g.:
        nexus_file_handler_callback = NexusFileCallback(parameters)
        run_engine.subscribe(nexus_file_handler_callback)
    Or decorate a plan using bluesky.preprocessors.subs_decorator.

    See: https://blueskyproject.io/bluesky/callbacks.html#ways-to-invoke-callbacks
    """

    def __init__(self, param_type: type[T]) -> None:
        """
        Construct a new instance of the callbacks.

        Args:
            param_type: Concrete type of the parameter model that will be deserialized in the start document.
        """
        super().__init__(NEXUS_LOGGER)
        self.param_type: type[T] = param_type
        self.run_start_uid: str | None = None
        self.descriptors: dict[str, EventDescriptor] = {}
        self.log = NEXUS_LOGGER
        self._writers: list[NexusWriter] = []

    def activity_gated_start(self, doc: RunStart):
        if doc.get("subplan_name") == PlanNameConstants.GRIDSCAN_OUTER:
            mx_bluesky_parameters = doc.get("mx_bluesky_parameters")
            detector_params_json = doc.get("detector_params")
            grid_scan_params_json = doc.get("grid_scan_parameters")
            assert isinstance(mx_bluesky_parameters, str)
            assert isinstance(detector_params_json, str)
            assert isinstance(grid_scan_params_json, str)
            NEXUS_LOGGER.info(
                f"Nexus writer received start document with experiment parameters {mx_bluesky_parameters}"
            )
            parameters: T = self.param_type.model_validate_json(mx_bluesky_parameters)
            detector_params = DetectorParams.model_validate_json(detector_params_json)
            grid_scan_params = GridScanParams.model_validate_json(grid_scan_params_json)
            self._writers = _create_writers_from_params(
                parameters, detector_params, grid_scan_params
            )

            self.run_start_uid = doc.get("uid")

    def activity_gated_descriptor(self, doc: EventDescriptor):
        self.descriptors[doc["uid"]] = doc

    def activity_gated_event(self, doc: Event) -> Event | None:
        event_descriptor = self.descriptors.get(doc["descriptor"])
        assert event_descriptor is not None
        if event_descriptor.get("name") == DocDescriptorNames.HARDWARE_READ_DURING:
            data = doc["data"]
            assert self._writers, "Nexus callback did not receive start doc"
            for nexus_writer in self._writers:
                (
                    nexus_writer.beam,
                    nexus_writer.attenuator,
                ) = create_beam_and_attenuator_parameters(
                    data["dcm-energy_in_keV"],
                    data["flux-flux_reading"],
                    data["attenuator-actual_transmission"],
                )
                vds_data_type = vds_type_based_on_bit_depth(
                    doc["data"]["eiger_bit_depth"]
                )
                nexus_writer.create_nexus_file(vds_data_type)
                NEXUS_LOGGER.info(f"Nexus file created at {nexus_writer.data_filename}")

        return super().activity_gated_event(doc)
