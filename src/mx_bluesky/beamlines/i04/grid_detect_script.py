from blueapi.core import BlueskyContext
from bluesky import preprocessors as bpp
from bluesky.run_engine import RunEngine
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.utils import get_beamline_based_on_environment_variable

from mx_bluesky.beamlines.i04.parameters.constants import CONST
from mx_bluesky.common.experiment_plans.oav_grid_detection_plan import (
    create_devices,
    grid_detection_plan,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import ispyb_activation_wrapper
from mx_bluesky.common.utils.log import (
    LOGGER,
    do_default_logging_setup,
)


def main():
    do_default_logging_setup(CONST.LOG_FILE_NAME, CONST.GRAYLOG_PORT, dev_mode=True)
    LOGGER.info("Testing grid_detection_plan on i04")
    context = setup_context(
        wait_for_connection=True,
    )
    composite = create_devices(context)
    parameters = OAVParameters(
        context="xrayCentring",
        oav_config_json="/dls_sw/i04/software/daq_configuration/json/OAVCentring.json",
    )
    RE = RunEngine(call_returns_result=True)

    @bpp.run_decorator()
    def my_plan():
        yield from ispyb_activation_wrapper(grid_detection_plan(
            composite=composite,
            parameters=parameters,
            snapshot_template="test_{angle}",
            snapshot_dir="/dls_sw/i04/software/bluesky/scratch",
            grid_width_microns=600,
            box_size_um=20,
            group=CONST,
        ), parameters)
    RE(my_plan())


def setup_context(wait_for_connection: bool = True) -> BlueskyContext:
    context = BlueskyContext()
    #context.with_plan_module(oav_grid_detection_plan)
    # context.with_plan_module(i04_plans)
    context.with_dodal_module(
        get_beamline_based_on_environment_variable(),
        wait_for_connection=wait_for_connection,
    )

    LOGGER.info(f"Plans found in context: {context.plan_functions.keys()}")
    return context


if __name__ == "__main__":
    main()
