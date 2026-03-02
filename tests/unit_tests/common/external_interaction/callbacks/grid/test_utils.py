from bluesky.run_engine import RunEngine
from dodal.devices.zocalo import ZocaloStartInfo

from mx_bluesky.common.external_interaction.callbacks.grid.utils import (
    generate_start_info_from_num_grids,
)
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan


def test_generate_start_info_from_num_grids(
    test_three_d_grid_params: SpecifiedThreeDGridScan, run_engine: RunEngine
):
    zocalo_info_gen = generate_start_info_from_num_grids(test_three_d_grid_params)
    next(zocalo_info_gen)
    infos = zocalo_info_gen.send({"_grid_num_to_id_map": {0: 0, 1: 1, 2: 2}})

    expected_infos = [
        ZocaloStartInfo(
            ispyb_dcid=num,
            filename=None,
            start_frame_index=test_three_d_grid_params.scan_indices[num],
            number_of_frames=len(test_three_d_grid_params.scan_points[num]),
            message_index=num,
        )
        for num in range(test_three_d_grid_params.num_grids)
    ]

    assert infos == expected_infos
