from pathlib import Path

from blueapi.core import BlueskyContext
from bluesky import preprocessors as bpp
from bluesky.run_engine import RunEngine
from dodal.utils import get_beamline_based_on_environment_variable
from pydantic_extra_types.semantic_version import SemanticVersion
from dodal.devices.aperturescatterguard import ApertureValue
from mx_bluesky.beamlines.i04.experiment_plans.i04_grid_detect_then_xray_centre_plan import (
    create_devices,
    i04_grid_detect_then_xray_centre,
)
from mx_bluesky.beamlines.i04.parameters.constants import CONST
from mx_bluesky.common.parameters.gridscan import GridCommon
from mx_bluesky.common.utils.log import (
    LOGGER,
    do_default_logging_setup,
)
from mx_bluesky.hyperion.parameters.gridscan import GridScanWithEdgeDetect


def main():
    do_default_logging_setup(CONST.LOG_FILE_NAME, CONST.GRAYLOG_PORT, dev_mode=True)
    LOGGER.info("Testing i04_grid_detect_then_xray_centre plan")

    context = setup_context(wait_for_connection=True)
    composite = create_devices(context)
    parameters = get_parameters()
    oav_config_json = "/dls_sw/i04/software/daq_configuration/json/OAVCentring.json"

    RE = RunEngine(call_returns_result=True)

    def my_plan():
        yield from (
            i04_grid_detect_then_xray_centre(
                composite=composite, parameters=parameters, oav_config=oav_config_json
            )
        )

    RE(my_plan())


def get_parameters():
    params = GridCommon(
        sample_id=6388287,
        parameter_model_version=SemanticVersion.validate_from_str("5.0.0"),
        visit="cm40608-2",
        snapshot_directory=Path(
            "/dls/i04/data/2025/cm40608-2/test_grid_scans/snapshots"
        ),
        file_name="test",
        storage_directory="/dls/i04/data/2025/cm40608-2/test_grid_scans2",
        exposure_time_s=0.005,
        detector_distance_mm=400,
        omega_start_deg=0.0,
        grid_width_um=600,
        transmission_frac=1.0,
        box_size_um=20,
        demand_energy_ev=13000,
        det_dist_to_beam_converter_path = "/dls_sw/i04/software/gda/config/lookupTables/DetDistToBeamXYConverter.txt",
        selected_aperture=ApertureValue.LARGE)

    return params


def setup_context(wait_for_connection: bool = True) -> BlueskyContext:
    context = BlueskyContext()
    # context.with_plan_module(oav_grid_detection_plan)
    # context.with_plan_module(i04_plans)
    context.with_dodal_module(
        get_beamline_based_on_environment_variable(),
        wait_for_connection=wait_for_connection,
    )

    LOGGER.info(f"Plans found in context: {context.plan_functions.keys()}")
    return context


if __name__ == "__main__":
    main()
