from __future__ import annotations

from collections.abc import Callable, Sequence
from time import time
from typing import TYPE_CHECKING, Any, TypeVar

from bluesky import preprocessors as bpp
from bluesky.utils import MsgGenerator, make_decorator

from mx_bluesky.common.external_interaction.callbacks.common.ispyb_callback_base import (
    BaseISPyBCallback,
)
from mx_bluesky.common.external_interaction.callbacks.common.ispyb_mapping import (
    populate_data_collection_group,
    populate_remaining_data_collection_info,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_mapping import (
    construct_comment_for_gridscan,
    populate_xy_data_collection_info,
    populate_xz_data_collection_info,
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
from mx_bluesky.common.parameters.constants import DocDescriptorNames, PlanNameConstants
from mx_bluesky.common.parameters.gridscan import (
    GridCommon,
)
from mx_bluesky.common.utils.exceptions import (
    ISPyBDepositionNotMade,
    SampleException,
)
from mx_bluesky.common.utils.log import ISPYB_ZOCALO_CALLBACK_LOGGER, set_dcgid_tag

if TYPE_CHECKING:
    from event_model import Event, RunStart, RunStop

T = TypeVar("T", bound="GridCommon")
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
        PlanNameConstants.ISPYB_ACTIVATION,
    )


ispyb_activation_decorator = make_decorator(ispyb_activation_wrapper)


class GridscanISPyBCallback(BaseISPyBCallback):
    """Callback class to handle the deposition of experiment parameters into the ISPyB
    database. Listens for 'event' and 'descriptor' documents. Creates the ISpyB entry on
    recieving an 'event' document for the 'ispyb_reading_hardware' event, and updates the
    deposition on recieving its final 'stop' document.

    To use, subscribe the Bluesky RunEngine to an instance of this class.
    E.g.:
        ispyb_handler_callback = FGSISPyBCallback(parameters)
        RE.subscribe(ispyb_handler_callback)
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
        self.ispyb_ids: IspybIds = IspybIds()
        self.param_type = param_type
        self._start_of_fgs_uid: str | None = None
        self._processing_start_time: float | None = None
        self.data_collection_group_info: DataCollectionGroupInfo | None

    def activity_gated_start(self, doc: RunStart):
        if doc.get("subplan_name") == PlanNameConstants.DO_FGS:
            self._start_of_fgs_uid = doc.get("uid")

        if doc.get("subplan_name") == PlanNameConstants.GRID_DETECT_AND_DO_GRIDSCAN:
            self.uid_to_finalize_on = doc.get("uid")
            ISPYB_ZOCALO_CALLBACK_LOGGER.info(
                "ISPyB callback received start document with experiment parameters and "
                f"uid: {self.uid_to_finalize_on}"
            )
            mx_bluesky_parameters = doc.get("mx_bluesky_parameters")
            assert isinstance(mx_bluesky_parameters, str)
            self.params = self.param_type.model_validate_json(mx_bluesky_parameters)
            self.ispyb = StoreInIspyb(self.ispyb_config)
            self.data_collection_group_info = populate_data_collection_group(
                self.params
            )

            scan_data_infos = [
                ScanDataInfo(
                    data_collection_info=populate_remaining_data_collection_info(
                        "MX-Bluesky: Xray centring 1 -",
                        None,
                        populate_xy_data_collection_info(
                            self.params.detector_params,
                        ),
                        self.params,
                    ),
                ),
                ScanDataInfo(
                    data_collection_info=populate_remaining_data_collection_info(
                        "MX-Bluesky: Xray centring 2 -",
                        None,
                        populate_xz_data_collection_info(self.params.detector_params),
                        self.params,
                    )
                ),
            ]

            self.ispyb_ids = self.ispyb.begin_deposition(
                self.data_collection_group_info, scan_data_infos
            )
            set_dcgid_tag(self.ispyb_ids.data_collection_group_id)
        return super().activity_gated_start(doc)

    def activity_gated_event(self, doc: Event):
        assert self.data_collection_group_info, ASSERT_START_BEFORE_EVENT_DOC_MESSAGE

        doc = super().activity_gated_event(doc)

        descriptor_name = self.descriptors[doc["descriptor"]].get("name")
        if descriptor_name == DocDescriptorNames.OAV_GRID_SNAPSHOT_TRIGGERED:
            scan_data_infos = self._handle_oav_grid_snapshot_triggered(doc)
            self.ispyb_ids = self.ispyb.update_deposition(
                self.ispyb_ids, scan_data_infos
            )
        self.ispyb.update_data_collection_group_table(
            self.data_collection_group_info, self.ispyb_ids.data_collection_group_id
        )

        return doc

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

    def _handle_oav_grid_snapshot_triggered(self, doc) -> Sequence[ScanDataInfo]:
        assert self.ispyb_ids.data_collection_ids, "No current data collection"
        assert self.params, "ISPyB handler didn't receive parameters!"
        assert self.data_collection_group_info, "No data collection group"
        data = doc["data"]
        data_collection_id = None
        data_collection_info = DataCollectionInfo(
            xtal_snapshot1=data.get("oav-grid_snapshot-last_path_full_overlay"),
            xtal_snapshot2=data.get("oav-grid_snapshot-last_path_outer"),
            xtal_snapshot3=data.get("oav-grid_snapshot-last_saved_path"),
            n_images=(
                data["oav-grid_snapshot-num_boxes_x"]
                * data["oav-grid_snapshot-num_boxes_y"]
            ),
        )
        microns_per_pixel_x = data["oav-microns_per_pixel_x"]
        microns_per_pixel_y = data["oav-microns_per_pixel_y"]
        data_collection_grid_info = DataCollectionGridInfo(
            dx_in_mm=data["oav-grid_snapshot-box_width"] * microns_per_pixel_x / 1000,
            dy_in_mm=data["oav-grid_snapshot-box_width"] * microns_per_pixel_y / 1000,
            steps_x=data["oav-grid_snapshot-num_boxes_x"],
            steps_y=data["oav-grid_snapshot-num_boxes_y"],
            microns_per_pixel_x=microns_per_pixel_x,
            microns_per_pixel_y=microns_per_pixel_y,
            snapshot_offset_x_pixel=int(data["oav-grid_snapshot-top_left_x"]),
            snapshot_offset_y_pixel=int(data["oav-grid_snapshot-top_left_y"]),
            orientation=Orientation.HORIZONTAL,
            snaked=True,
        )
        data_collection_info.comments = construct_comment_for_gridscan(
            data_collection_grid_info
        )

        if self.data_collection_group_info.comments:
            self.data_collection_group_info.comments += (
                f"by {data_collection_grid_info.steps_y}."
            )
        else:
            self.data_collection_group_info.comments = (
                f"Diffraction grid scan of "
                f"{data_collection_grid_info.steps_x} "
                f"by {data_collection_grid_info.steps_y} "
            )

        if len(self.ispyb_ids.data_collection_ids) > self._oav_snapshot_event_idx:
            data_collection_id = self.ispyb_ids.data_collection_ids[
                self._oav_snapshot_event_idx
            ]
        self._populate_axis_info(data_collection_info, doc["data"]["smargon-omega"])

        scan_data_info = ScanDataInfo(
            data_collection_info=data_collection_info,
            data_collection_id=data_collection_id,
            data_collection_grid_info=data_collection_grid_info,
        )
        ISPYB_ZOCALO_CALLBACK_LOGGER.info(
            "Updating ispyb data collection after oav snapshot."
        )
        self._oav_snapshot_event_idx += 1
        return [scan_data_info]

    def _populate_axis_info(
        self, data_collection_info: DataCollectionInfo, omega_start: float | None
    ):
        if omega_start is not None:
            omega_in_gda_space = -omega_start
            data_collection_info.omega_start = omega_in_gda_space
            data_collection_info.axis_start = omega_in_gda_space
            data_collection_info.axis_end = omega_in_gda_space
            data_collection_info.axis_range = 0

    def populate_info_for_update(
        self,
        event_sourced_data_collection_info: DataCollectionInfo,
        event_sourced_position_info: DataCollectionPositionInfo | None,
        params: DiffractionExperimentWithSample,
    ) -> Sequence[ScanDataInfo]:
        assert self.ispyb_ids.data_collection_ids, (
            "Expect at least one valid data collection to record scan data"
        )
        xy_scan_data_info = ScanDataInfo(
            data_collection_info=event_sourced_data_collection_info,
            data_collection_id=self.ispyb_ids.data_collection_ids[0],
        )
        scan_data_infos = [xy_scan_data_info]

        data_collection_id = (
            self.ispyb_ids.data_collection_ids[1]
            if len(self.ispyb_ids.data_collection_ids) > 1
            else None
        )
        xz_scan_data_info = ScanDataInfo(
            data_collection_info=event_sourced_data_collection_info,
            data_collection_id=data_collection_id,
        )
        scan_data_infos.append(xz_scan_data_info)
        return scan_data_infos

    def activity_gated_stop(self, doc: RunStop) -> RunStop:
        assert self.data_collection_group_info, (
            f"No data collection group info - stop document has been emitted before a {PlanNameConstants.GRID_DETECT_AND_DO_GRIDSCAN} start document"
        )
        if doc.get("run_start") == self._start_of_fgs_uid:
            self._processing_start_time = time()
        if doc.get("run_start") == self.uid_to_finalize_on:
            ISPYB_ZOCALO_CALLBACK_LOGGER.info(
                "ISPyB callback received stop document corresponding to start document "
                f"with uid: {self.uid_to_finalize_on}."
            )
            if self.ispyb_ids == IspybIds():
                raise ISPyBDepositionNotMade("ispyb was not initialised at run start")
            exception_type, message = SampleException.type_and_message_from_reason(
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
            return super().activity_gated_stop(doc)
        return self._tag_doc(doc)
