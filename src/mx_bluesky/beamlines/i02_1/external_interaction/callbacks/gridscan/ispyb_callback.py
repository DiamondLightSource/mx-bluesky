from __future__ import annotations

from collections.abc import Callable, Sequence
from time import time
from typing import TYPE_CHECKING, Any, TypeVar

from bluesky import preprocessors as bpp
from bluesky.utils import MsgGenerator, make_decorator

from mx_bluesky.beamlines.i02_1.i02_1_gridscan_plan import I02_1FgsParams
from mx_bluesky.common.external_interaction.callbacks.common.ispyb_callback_base import (
    BaseISPyBCallback,
    D,
)
from mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping import (
    populate_data_collection_group,
    populate_remaining_data_collection_info,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    GridscanPlane,
    _smargon_omega_to_xyxz_plane,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_mapping import (
    construct_comment_for_gridscan,
)
from mx_bluesky.common.external_interaction.ispyb.data_model import (
    DataCollectionGridInfo,
    DataCollectionGroupInfo,
    DataCollectionInfo,
    DataCollectionPositionInfo,
    Orientation,
    ScanDataInfo,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_store import (
    IspybIds,
    StoreInIspyb,
)
from mx_bluesky.common.parameters.components import DiffractionExperimentWithSample
from mx_bluesky.common.parameters.constants import PlanNameConstants
from mx_bluesky.common.utils.exceptions import (
    ISPyBDepositionNotMadeError,
    SampleError,
)
from mx_bluesky.common.utils.log import ISPYB_ZOCALO_CALLBACK_LOGGER, set_dcgid_tag

if TYPE_CHECKING:
    from event_model import RunStart, RunStop

T = TypeVar("T", bound="I02_1FgsParams")
ASSERT_START_BEFORE_EVENT_DOC_MESSAGE = f"No data collection group info - event document has been emitted before a {PlanNameConstants.GRID_DETECT_AND_DO_GRIDSCAN} start document"


def ispyb_activation_wrapper(plan_generator: MsgGenerator, parameters):
    return bpp.set_run_key_wrapper(
        bpp.run_wrapper(
            plan_generator,
            md={
                "activate_callbacks": ["GridscanISPyBCallback"],
                "subplan_name": PlanNameConstants.GRID_DETECT_AND_DO_GRIDSCAN,
                "mx_bluesky_parameters": parameters.model_dump_json(),
            },
        ),
        PlanNameConstants.GRID_DETECT_AND_DO_GRIDSCAN,
    )


ispyb_activation_decorator = make_decorator(ispyb_activation_wrapper)


class GridscanISPyBCallback(BaseISPyBCallback):
    """Callback class to handle the deposition of experiment parameters into the ISPyB
    database. Listens for 'event' and 'descriptor' documents. Creates the ISpyB entry on
    receiving an 'event' document for the 'ispyb_reading_hardware' event, and updates the
    deposition on receiving its final 'stop' document.

    To use, subscribe the Bluesky RunEngine to an instance of this class.
    E.g.:
        ispyb_handler_callback = FGSISPyBCallback(parameters)
        run_engine.subscribe(ispyb_handler_callback)
    Or decorate a plan using bluesky.preprocessors.subs_decorator.

    See: https://blueskyproject.io/bluesky/callbacks.html#ways-to-invoke-callbacks
    """

    def __init__(
        self,
        param_type: type[T],
        *,
        emit: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(emit=emit)
        self.ispyb: StoreInIspyb
        self.param_type = param_type
        self._start_of_fgs_uid: str | None = None
        self._processing_start_time: float | None = None
        self._grid_plane_to_id_map: dict[GridscanPlane, int] = {}
        self._grid_plane_to_width_map: dict[GridscanPlane, int] = {}
        self.data_collection_group_info: DataCollectionGroupInfo | None

    def activity_gated_start(self, doc: RunStart):
        if doc.get("subplan_name") == PlanNameConstants.DO_FGS:
            self._start_of_fgs_uid = doc.get("uid")
            ISPYB_ZOCALO_CALLBACK_LOGGER.info(
                "ISPyB callback received start document with experiment parameters and "
                f"uid: {self._start_of_fgs_uid}"
            )
            mx_bluesky_parameters = doc.get("mx_bluesky_parameters")
            assert isinstance(mx_bluesky_parameters, str)
            self.params = self.param_type.model_validate_json(mx_bluesky_parameters)
            assert isinstance(self.params, I02_1FgsParams)
            self.ispyb = StoreInIspyb(self.ispyb_config)
            self.data_collection_group_info = populate_data_collection_group(
                self.params
            )

            # todo fix this: define scan_data_infos here and then overwrite later
            scan_data_infos = []
            assert self.params.num_grids > 0
            for grid in range(self.params.num_grids):
                scan_data_infos.append(
                    ScanDataInfo(
                        data_collection_info=populate_remaining_data_collection_info(
                            f"MX-Bluesky: Xray centring {grid + 1}/{self.params.num_grids} -",
                            None,
                            DataCollectionInfo(),
                            self.params,
                        )
                    )
                )

            # todo make a function which populates all of this. "fill deposition with grid info"

            self.ispyb_ids = self.ispyb.begin_deposition(
                self.data_collection_group_info, scan_data_infos
            )
            # Use grid information given by GDA to complete ispyb info
            scan_data_infos = self._get_scan_infos(doc)
            self.ispyb_ids = self.ispyb.update_deposition(
                self.ispyb_ids, scan_data_infos
            )
            self.ispyb.update_data_collection_group_table(
                self.data_collection_group_info, self.ispyb_ids.data_collection_group_id
            )

            set_dcgid_tag(self.ispyb_ids.data_collection_group_id)
        return super().activity_gated_start(doc)

    def _add_processing_time_to_comment(self, processing_start_time: float):
        assert self.data_collection_group_info, ASSERT_START_BEFORE_EVENT_DOC_MESSAGE
        proc_time = time() - processing_start_time
        crystal_summary = f"Zocalo processing took {proc_time:.2f} s."

        self.data_collection_group_info.comments = (
            self.data_collection_group_info.comments or ""
        ) + crystal_summary

        self.ispyb.append_to_comment(
            self.ispyb_ids.data_collection_ids[0], crystal_summary
        )

    def _get_scan_infos(self, doc) -> Sequence[ScanDataInfo]:
        """
        so grid information is available immediately after the plan is triggered.
        In contrast, i03 and i04 use the OAV to automatically detect their grid.
        """
        assert isinstance(self.params, I02_1FgsParams)
        assert self.ispyb_ids.data_collection_ids, "No current data collection"
        assert self.data_collection_group_info, "No data collection group"
        data = doc["data"]
        scan_data_infos = []

        for grid_num in range(self.params.num_grids):
            omega = data.get("gonio-omega", self.params.omega_starts_deg[grid_num])

            # Don't need to do deal with the grid plane here since vmxm only do
            # one plane, but leave it in so it's easier to standardise in the future
            grid_plane = _smargon_omega_to_xyxz_plane(omega)
            ISPYB_ZOCALO_CALLBACK_LOGGER.info(
                f"Generating dc info for gridplane {grid_plane}, omega {omega}"
            )
            data_collection_number = self.data_collection_number_from_gridplane(
                grid_plane
            )
            file_template = f"{self.params.detector_params.prefix}_{data_collection_number}_master.h5"
            # Snapshots have already been taken in GDA
            data_collection_info = DataCollectionInfo(
                xtal_snapshot1=str(self.params.path_to_xtal_snapshot),
                xtal_snapshot2=str(self.params.path_to_xtal_snapshot),
                xtal_snapshot3=str(self.params.path_to_xtal_snapshot),
                n_images=self.params.num_images,
                data_collection_number=data_collection_number,
                file_template=file_template,
            )
            data_collection_grid_info = DataCollectionGridInfo(
                dx_in_mm=self.params.x_step_size_um * 1000,
                dy_in_mm=self.params.y_step_sizes_um[grid_num] * 1000,
                steps_x=self.params.x_steps,
                steps_y=self.params.y_steps[grid_num],
                microns_per_pixel_x=self.params.microns_per_pixel_x,
                microns_per_pixel_y=self.params.microns_per_pixel_y,
                snapshot_offset_x_pixel=self.params.upper_left_x,
                snapshot_offset_y_pixel=self.params.upper_left_y,
                orientation=Orientation.HORIZONTAL,
                snaked=True,
            )
            data_collection_info.comments = construct_comment_for_gridscan(
                data_collection_grid_info
            )

            # Grid plane logic isn't needed for VMX, but keep it for now anyway
            data_collection_id = self.ispyb_ids.data_collection_ids[
                0 if grid_plane == GridscanPlane.OMEGA_XY else 1
            ]
            self._grid_plane_to_id_map[grid_plane] = data_collection_id
            self._grid_plane_to_width_map[grid_plane] = (
                data_collection_grid_info.steps_y
            )

            y_steps = self._grid_plane_to_width_map.get(GridscanPlane.OMEGA_XY, "_")
            self.data_collection_group_info.comments = (
                f"Diffraction grid scan of {data_collection_grid_info.steps_x} by "
                f"{y_steps}."
            )

            self._populate_axis_info(data_collection_info, doc["data"])

            # todo do all this stuff as soon as possible after plan starts

            scan_data_info = ScanDataInfo(
                data_collection_info=data_collection_info,
                data_collection_id=data_collection_id,
                data_collection_grid_info=data_collection_grid_info,
            )

            scan_data_infos.append(scan_data_info)

        ISPYB_ZOCALO_CALLBACK_LOGGER.info(
            "Updating ispyb data collection after loading grid params"
        )

        return scan_data_infos

    def _populate_axis_info(self, data_collection_info: DataCollectionInfo, doc: dict):
        if (omega_start := doc.get("gonio-omega")) is not None:
            omega_in_gda_space = -omega_start
            data_collection_info.omega_start = omega_in_gda_space
            data_collection_info.axis_start = omega_in_gda_space
            data_collection_info.axis_end = omega_in_gda_space
            data_collection_info.axis_range = 0
        if (chi_start := doc.get("gonio-chi")) is not None:
            data_collection_info.chi_start = chi_start

    def populate_info_for_update(
        self,
        event_sourced_data_collection_info: DataCollectionInfo,
        event_sourced_position_info: DataCollectionPositionInfo | None,
        params: DiffractionExperimentWithSample,
    ) -> Sequence[ScanDataInfo]:
        assert self.ispyb_ids.data_collection_ids, (
            "Expect at least one valid data collection to record scan data"
        )
        assert isinstance(self.params, I02_1FgsParams)
        scan_data_infos = []
        for grid_num in range(self.params.num_grids):
            scan_data_info = ScanDataInfo(
                data_collection_info=event_sourced_data_collection_info,
                data_collection_id=self.ispyb_ids.data_collection_ids[grid_num],
            )
            scan_data_infos.append(scan_data_info)
        return scan_data_infos

    def activity_gated_stop(self, doc: RunStop) -> RunStop:
        assert self.data_collection_group_info, (
            f"No data collection group info - stop document has been emitted before a {PlanNameConstants.GRID_DETECT_AND_DO_GRIDSCAN} start document"
        )
        if doc.get("run_start") == self._start_of_fgs_uid:
            self._processing_start_time = time()
        if doc.get("run_start") == self._start_of_fgs_uid:
            ISPYB_ZOCALO_CALLBACK_LOGGER.info(
                "ISPyB callback received stop document corresponding to start document "
                f"with uid: {self._start_of_fgs_uid}."
            )
            if self.ispyb_ids == IspybIds():
                raise ISPyBDepositionNotMadeError(
                    "ispyb was not initialised at run start"
                )
            exception_type, message = SampleError.type_and_message_from_reason(
                doc.get("reason", "")
            )
            if exception_type:
                doc["reason"] = message
                self.data_collection_group_info.comments = message
            elif self._processing_start_time:
                self._add_processing_time_to_comment(self._processing_start_time)
            self.ispyb.update_data_collection_group_table(
                self.data_collection_group_info,
                self.ispyb_ids.data_collection_group_id,
            )
            self.data_collection_group_info = None
            self._grid_plane_to_id_map.clear()
            self._grid_plane_to_width_map.clear()
            return super().activity_gated_stop(doc)
        return self.tag_doc(doc)

    def tag_doc(self, doc: D) -> D:
        doc = super().tag_doc(doc)
        assert isinstance(doc, dict)
        if self._grid_plane_to_id_map:
            doc["grid_plane_to_id_map"] = self._grid_plane_to_id_map
        return doc  # type: ignore

    def data_collection_number_from_gridplane(self, plane) -> int:
        assert self.params
        base_number = self.params.detector_params.run_number
        return base_number if plane == GridscanPlane.OMEGA_XY else base_number + 1
