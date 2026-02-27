from __future__ import annotations

from abc import abstractmethod
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
from mx_bluesky.common.external_interaction.callbacks.grid.utils import (
    common_add_processing_time_to_comment,
    common_populate_axis_info,
)
from mx_bluesky.common.external_interaction.ispyb.data_model import (
    DataCollectionGroupInfo,
    DataCollectionInfo,
    DataCollectionPositionInfo,
    ScanDataInfo,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_store import (
    IspybIds,
    StoreInIspyb,
)
from mx_bluesky.common.parameters.components import DiffractionExperimentWithSample
from mx_bluesky.common.parameters.constants import PlanNameConstants
from mx_bluesky.common.parameters.gridscan import SpecifiedGrids
from mx_bluesky.common.utils.exceptions import (
    ISPyBDepositionNotMadeError,
    SampleError,
)
from mx_bluesky.common.utils.log import ISPYB_ZOCALO_CALLBACK_LOGGER, set_dcgid_tag

if TYPE_CHECKING:
    from event_model import RunStart, RunStop

T = TypeVar("T", bound="SpecifiedGrids")
D = TypeVar("D")


def ispyb_activation_wrapper(plan_generator: MsgGenerator, parameters):
    return bpp.set_run_key_wrapper(
        bpp.run_wrapper(
            plan_generator,
            md={
                "activate_callbacks": ["GridscanISPyBCallback"],
                "subplan_name": PlanNameConstants.TRIGGER_GRIDSCAN_ISPYB_CALLBACK,
                "mx_bluesky_parameters": parameters.model_dump_json(),
            },
        ),
        PlanNameConstants.TRIGGER_GRIDSCAN_ISPYB_CALLBACK,
    )


ispyb_activation_decorator = make_decorator(ispyb_activation_wrapper)


class GridscanISPyBCallback(BaseISPyBCallback):
    """Callback class to handle the deposition of experiment parameters into the ISPyB
    database. Listens for 'event' and 'descriptor' documents. Creates the ISpyB entry on
    receiving an 'event' document for the 'ispyb_reading_hardware' event, and updates the
    deposition on receiving its final 'stop' document.

    This callback should be used when grid parameters have been sent in to BlueAPI as part
    of entry parameters.

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
        self._grid_num_to_id_map: dict[int, int] = {}
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

            # Fill ispyb deposition with all relevant info, including grid info
            self.fill_gridscan_deposition_and_store(lambda: self._get_scan_infos(doc))

            set_dcgid_tag(self.ispyb_ids.data_collection_group_id)
        return super().activity_gated_start(doc)

    def _add_processing_time_to_comment(self, processing_start_time: float):
        common_add_processing_time_to_comment(
            self, processing_start_time, self.data_collection_group_info
        )

    @abstractmethod
    def _get_scan_infos(self, doc) -> Sequence[ScanDataInfo]: ...

    """
        Use grid parameters to create a sequence of ScanDataInfos. See
        i02-1's gridscan ispyb callback for example implementation.
    """

    def _populate_axis_info(self, data_collection_info: DataCollectionInfo, doc: dict):
        common_populate_axis_info(data_collection_info, doc)

    def populate_info_for_update(
        self,
        event_sourced_data_collection_info: DataCollectionInfo,
        event_sourced_position_info: DataCollectionPositionInfo | None,
        params: DiffractionExperimentWithSample,
    ) -> Sequence[ScanDataInfo]:
        assert self.ispyb_ids.data_collection_ids, (
            "Expect at least one valid data collection to record scan data"
        )
        assert isinstance(self.params, SpecifiedGrids)
        scan_data_infos = []
        for grid_num in range(self.params.num_grids):
            id = self.ispyb_ids.data_collection_ids[grid_num]
            self._grid_num_to_id_map[grid_num] = id
            scan_data_info = ScanDataInfo(
                data_collection_info=event_sourced_data_collection_info,
                data_collection_id=id,
            )
            scan_data_infos.append(scan_data_info)
        return scan_data_infos

    def activity_gated_stop(self, doc: RunStop) -> RunStop:
        assert self.data_collection_group_info, (
            f"No data collection group info - stop document has been emitted before a {PlanNameConstants.DO_FGS} start document"
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
            return super().activity_gated_stop(doc)
        return self.tag_doc(doc)

    def tag_doc(self, doc: D) -> D:
        doc = super().tag_doc(doc)
        assert isinstance(doc, dict)
        if self._grid_num_to_id_map:
            doc["_grid_num_to_id_map"] = self._grid_num_to_id_map
        return doc  # type: ignore

    def data_collection_number_from_gridplane(self, plane) -> int:
        assert self.params
        return self.params.detector_params.run_number

    def fill_gridscan_deposition_and_store(
        self, make_scan_infos_with_grid_info: Callable[..., Sequence[ScanDataInfo]]
    ):
        assert isinstance(self.params, SpecifiedGrids)

        # Do initial deposition using all info except grid info
        self.ispyb = StoreInIspyb(self.ispyb_config)
        self.data_collection_group_info = populate_data_collection_group(self.params)
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
        self.ispyb_ids = self.ispyb.begin_deposition(
            self.data_collection_group_info, scan_data_infos
        )
        # Now use grid information to complete deposition
        scan_data_infos_list: list[ScanDataInfo] = list(
            make_scan_infos_with_grid_info()
        )
        self.ispyb_ids = self.ispyb.update_deposition(
            self.ispyb_ids, scan_data_infos_list
        )
        self.ispyb.update_data_collection_group_table(
            self.data_collection_group_info, self.ispyb_ids.data_collection_group_id
        )
