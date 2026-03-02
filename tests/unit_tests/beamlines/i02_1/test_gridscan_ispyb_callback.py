from mx_bluesky.beamlines.i02_1.composites import I02_1FgsParams
from mx_bluesky.beamlines.i02_1.external_interaction.callbacks.gridscan.ispyb_callback import (
    GridscanISPyBCallback,
    _make_comment,
)
from mx_bluesky.common.external_interaction.callbacks.grid.grid_detect_and_scan.ispyb_mapping import (
    construct_comment_for_gridscan,
)
from mx_bluesky.common.external_interaction.ispyb.data_model import (
    DataCollectionGridInfo,
    DataCollectionGroupInfo,
    DataCollectionInfo,
    Orientation,
    ScanDataInfo,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_store import IspybIds


def _get_expected_scan_info(params: I02_1FgsParams, dcid: int):
    dc_grid_info = DataCollectionGridInfo(
        params.x_step_size_um * 1000,
        params.y_step_sizes_um[0] * 1000,
        params.x_steps,
        params.y_steps[0],
        params.microns_per_pixel_x,
        params.microns_per_pixel_y,
        params.upper_left_x,
        params.upper_left_y,
        Orientation.HORIZONTAL,
        True,
    )
    xtal = str(params.path_to_xtal_snapshot)
    dc_info = DataCollectionInfo(
        omega_start=0,
        data_collection_number=1,
        xtal_snapshot1=xtal,
        xtal_snapshot2=xtal,
        xtal_snapshot3=xtal,
        n_images=params.x_steps * params.y_steps[0],
        axis_end=0,
        axis_range=0,
        axis_start=0,
        file_template=f"{params.file_name}_1_master.h5",
        comments=construct_comment_for_gridscan(dc_grid_info),
    )
    return [
        ScanDataInfo(
            data_collection_info=dc_info,
            data_collection_id=dcid,
            data_collection_grid_info=dc_grid_info,
        )
    ]


def test_get_scan_infos_gives_expected_output(
    fgs_params_two_d: I02_1FgsParams,
):
    callback = GridscanISPyBCallback(param_type=I02_1FgsParams)
    callback.params = fgs_params_two_d
    doc = {}
    doc["data"] = {
        "gonio-omega": 0,
    }
    callback.ispyb_ids = IspybIds()
    callback.ispyb_ids.data_collection_group_id = 0
    callback.ispyb_ids.data_collection_ids = ((0),)
    callback.data_collection_group_info = DataCollectionGroupInfo(
        "0",
        "SAD",
        None,
        comments=_make_comment(fgs_params_two_d.x_steps, fgs_params_two_d.y_steps[0]),
    )
    scan_info = callback._get_scan_infos(doc)
    assert scan_info[0].data_collection_grid_info

    assert scan_info == _get_expected_scan_info(fgs_params_two_d, 0)
