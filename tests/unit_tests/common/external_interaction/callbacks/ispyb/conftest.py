from copy import deepcopy

import pytest

from mx_bluesky.common.external_interaction.ispyb.data_model import (
    DataCollectionGridInfo,
    DataCollectionPositionInfo,
    Orientation,
    ScanDataInfo,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_store import StoreInIspyb
from mx_bluesky.hyperion.parameters.gridscan import HyperionSpecifiedThreeDGridScan

from ......conftest import (
    TEST_DATA_COLLECTION_GROUP_ID,
    TEST_DATA_COLLECTION_IDS,
    TEST_SAMPLE_ID,
    default_raw_gridscan_params,
)


@pytest.fixture
def dummy_params():
    dummy_params = HyperionSpecifiedThreeDGridScan(**default_raw_gridscan_params())
    dummy_params.sample_id = TEST_SAMPLE_ID
    dummy_params.run_number = 0
    return dummy_params


@pytest.fixture
def dummy_ispyb(ispyb_config_path: str) -> StoreInIspyb:
    return StoreInIspyb(ispyb_config_path)


@pytest.fixture
def scan_xy_data_info_for_update(
    scan_data_info_for_begin: ScanDataInfo,
) -> ScanDataInfo:
    scan_data_info_for_update = deepcopy(scan_data_info_for_begin)
    scan_data_info_for_update.data_collection_info.parent_id = (
        TEST_DATA_COLLECTION_GROUP_ID
    )
    scan_data_info_for_update.data_collection_info.synchrotron_mode = "test"
    scan_data_info_for_update.data_collection_info.flux = 10
    scan_data_info_for_update.data_collection_grid_info = DataCollectionGridInfo(
        dx_in_mm=0.1,
        dy_in_mm=0.1,
        steps_x=40,
        steps_y=20,
        microns_per_pixel_x=1.25,
        microns_per_pixel_y=1.25,
        snapshot_offset_x_pixel=100,
        snapshot_offset_y_pixel=100,
        orientation=Orientation.HORIZONTAL,
        snaked=True,
    )
    scan_data_info_for_update.data_collection_position_info = (
        DataCollectionPositionInfo(0, 0, 0)
    )
    scan_data_info_for_update.data_collection_id = TEST_DATA_COLLECTION_IDS[0]
    return scan_data_info_for_update
