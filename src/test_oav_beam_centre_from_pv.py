import bluesky.plan_stubs as bps
import pydantic
from blueapi.core import BlueskyContext
from bluesky import RunEngine
from dodal.devices.oav.oav_detector import OAV, OAVBeamCentrePV
from dodal.utils import get_beamline_based_on_environment_variable

from mx_bluesky.common.utils.context import device_composite_from_context
from mx_bluesky.common.utils.log import (
    LOGGER,
    do_default_logging_setup,
)
from mx_bluesky.hyperion.parameters.constants import CONST


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class JustOav:
    """All devices which are directly or indirectly required by this plan"""

    oav: OAV
    oav_full_screen: OAV


def main():
    context = setup_context(wait_for_connection=True)
    composite = create_devices(context)

    do_default_logging_setup(CONST.LOG_FILE_NAME, CONST.GRAYLOG_PORT, dev_mode=False)
    # oav = i04.oav()
    assert isinstance(composite.oav, OAVBeamCentrePV)
    assert isinstance(composite.oav_full_screen, OAVBeamCentrePV)
    LOGGER.info("Starting")
    RE = RunEngine(call_returns_result=True)
    RE(my_plan(composite))


def my_plan(comosite: JustOav):
    response = ""
    while response != "q":
        response = input()
        i = yield from bps.rd(comosite.oav.beam_centre_i)
        j = yield from bps.rd(comosite.oav.beam_centre_j)
        i_fs = yield from bps.rd(comosite.oav_full_screen.beam_centre_i)
        j_fs = yield from bps.rd(comosite.oav_full_screen.beam_centre_j)

        LOGGER.info(f"Found beam centre for oav: ({i}, {j}).")
        LOGGER.info(f"Found beam centre for oav_full_screen: ({i_fs}, {j_fs}).")


def create_devices(
    context: BlueskyContext,
) -> JustOav:
    return device_composite_from_context(context, JustOav)


def setup_context(wait_for_connection: bool = True) -> BlueskyContext:
    context = BlueskyContext()
    context.with_dodal_module(
        get_beamline_based_on_environment_variable(),
        wait_for_connection=wait_for_connection,
    )

    LOGGER.info(f"Plans found in context: {context.plan_functions.keys()}")
    return context


if __name__ == "__main__":
    main()
