from pathlib import Path
from unittest.mock import MagicMock

from blueapi.core import BlueskyContext
from bluesky import preprocessors as bpp
from bluesky.run_engine import RunEngine
from dodal.devices.detector import DetectorParams
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.utils import get_beamline_based_on_environment_variable
from pydantic_extra_types.semantic_version import SemanticVersion

from mx_bluesky.beamlines.i04.parameters.constants import CONST
from mx_bluesky.common.external_interaction.callbacks.common.callback_util import create_gridscan_callbacks
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import ispyb_activation_wrapper
from mx_bluesky.common.utils.log import (
    LOGGER,
    do_default_logging_setup,
)
from mx_bluesky.hyperion.experiment_plans.grid_detect_then_xray_centre_plan import (
    create_devices,
    detect_grid_and_do_gridscan,
)
from mx_bluesky.hyperion.parameters.gridscan import GridScanWithEdgeDetect


def main():
    do_default_logging_setup(CONST.LOG_FILE_NAME, CONST.GRAYLOG_PORT, dev_mode=False)
    context = setup_context(
        wait_for_connection=True,
    )
    detector_params = DetectorParams(
        exposure_time_s=0.005,
        directory="/dls/i04/data/2025/cm40608-2/test_grid_scans",
        prefix="test",
        detector_distance=1000,
        omega_start=0,
        omega_increment=0,
        num_images_per_trigger=1,
        num_triggers=10,
        use_roi_mode=True,
        det_dist_to_beam_converter_path="/dls_sw/i03/software/daq_configuration/lookup/DetDistToBeamXYConverter.txt",
        expected_energy_ev = 13000
    )
    composite = create_devices(context)

    parameters = GridScanWithEdgeDetect(
        sample_id=6388287,
        parameter_model_version=SemanticVersion.validate_from_str("5.0.0"),
        visit="cm40608-2",
        snapshot_directory=Path(
            "/dls/i04/data/2025/cm40608-2/test_grid_scans/snapshots"
        ),
        file_name="test",
        storage_directory="/dls/i04/data/2025/cm40608-2/test_grid_scans2",
        exposure_time_s=0.005,
        detector_distance_mm=1000,
        omega_start_deg=0.0,
        grid_width_um=600,
        transmission_frac=1.0,
        box_size_um=20,
    )
    oav_params = OAVParameters(
        context="xrayCentring",
        oav_config_json="/dls_sw/i04/software/daq_configuration/json/OAVCentring.json",
    )
    parameters.box_size_um = 20
    parameters.grid_width_um = 600
    parameters.demand_energy_ev = 13000
    RE = RunEngine(call_returns_result=True)

    @bpp.subs_decorator(create_gridscan_callbacks())
    @bpp.run_decorator()
    def my_plan():
        yield from ispyb_activation_wrapper(detect_grid_and_do_gridscan(
            composite=composite,
            parameters=parameters,
            oav_params=oav_params,
            group=CONST), parameters)
        

    RE(my_plan())


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
