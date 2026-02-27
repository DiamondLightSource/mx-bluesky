from collections.abc import Sequence

from mx_bluesky.beamlines.i02_1.composites import I02_1FgsParams
from mx_bluesky.common.external_interaction.callbacks.grid.grid_detect_and_scan.ispyb_mapping import (
    construct_comment_for_gridscan,
)
from mx_bluesky.common.external_interaction.callbacks.grid.gridscan.ispyb_callback import (
    GridscanISPyBCallback,
)
from mx_bluesky.common.external_interaction.ispyb.data_model import (
    DataCollectionGridInfo,
    DataCollectionInfo,
    Orientation,
    ScanDataInfo,
)
from mx_bluesky.common.utils.log import ISPYB_ZOCALO_CALLBACK_LOGGER


class I021GridscanISPyBCallback(GridscanISPyBCallback):
    def _get_scan_infos(self, doc) -> Sequence[ScanDataInfo]:
        """
        For VMXm, grid information is available immediately after the plan is triggered.
        """
        assert isinstance(self.params, I02_1FgsParams)
        assert self.ispyb_ids.data_collection_ids, "No current data collection"
        assert self.data_collection_group_info, "No data collection group"
        data = doc["data"]
        scan_data_infos = []

        for grid_num in range(self.params.num_grids):
            omega = data.get("gonio-omega", self.params.omega_starts_deg[grid_num])

            ISPYB_ZOCALO_CALLBACK_LOGGER.info(
                f"Generating dc info for gridplane XY, omega {omega}"
            )
            data_collection_number = self.params.detector_params.run_number
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

            data_collection_id = self.ispyb_ids.data_collection_ids[0]

            self.data_collection_group_info.comments = (
                f"Diffraction grid scan of {data_collection_grid_info.steps_x} by "
                f"{self.params.y_steps}."
            )

            self._populate_axis_info(data_collection_info, doc["data"])

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
