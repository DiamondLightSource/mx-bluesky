"""
TODO:
- Get good way to setup logging on plan startup


This overall plan should:
- Setup graylog (for now), and link to https://github.com/DiamondLightSource/blueapi/issues/583
- Do snapshots (maybe in different ticket)
- Accept grid scan params from GDA
- Do FGS and trigger zocalo but don't wait on zocalo
- Push results to ispyb

-Should we also automatically move to the centre of the crystal? Probably not as vmxm mainly use FGS just to check if crystal diffracts. (ask though)

- see https://github.com/DiamondLightSource/hyperion/pull/942/files to see what old plan was doing
- see https://github.com/DiamondLightSource/dodal/pull/211 for the old dodal change


Create common interface for all this stuff so that all this shared logic between hyperion isn't duplicated
"""

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import pydantic
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.attenuator.attenuator import EnumFilterAttenuator
from dodal.devices.backlight import Backlight
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import ZebraFastGridScan
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zocalo import ZocaloResults
from dodal.devices.zocalo.zocalo_results import (
    ZOCALO_READING_PLAN_NAME,
    ZOCALO_STAGE_GROUP,
    ZocaloResults,
    get_full_processing_results,
)

from mx_bluesky.beamlines.i02_1.device_setup_plans.setup_zebra import (
    setup_zebra_for_xrc_flyscan,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    ispyb_activation_wrapper,
)
from mx_bluesky.common.parameters.constants import (
    EnvironmentConstants,
    PlanNameConstants,
)
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.xrc_result import XRayCentreEventHandler
from mx_bluesky.hyperion.device_setup_plans.xbpm_feedback import (
    transmission_and_xbpm_feedback_for_collection_decorator,
)

# TODO: identify the differences:
"""
in VMXM: We don't need the aperture scatterguard - don't move aperture
Slit gaps and dcm and undulator may not be needed to be read, so different read hardware plan
Don't use panda - different setup and tidy
Sample shutter - unclear how this works for vmxm



"""


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class FlyScanXRayCentreComposite:
    """All devices which are directly or indirectly required by this plan"""

    attenuator: EnumFilterAttenuator
    backlight: Backlight
    eiger: EigerDetector
    zebra_fast_grid_scan: ZebraFastGridScan
    synchrotron: Synchrotron
    xbpm_feedback: XBPMFeedback
    zebra: Zebra
    zocalo: ZocaloResults
    smargon: Smargon

    @property
    def sample_motors(self) -> Smargon:
        """Convenience alias with a more user-friendly name"""
        return self.smargon


def flyscan_xray_centre(
    parameters: SpecifiedThreeDGridScan,
    attenuator: EnumFilterAttenuator = inject("attenuator"),
    backlight: Backlight = inject("backlight"),
    eiger: EigerDetector = inject("eiger"),
    zebra_fast_grid_scan: ZebraFastGridScan = inject("zebra_fast_grid_scan"),
    synchrotron: Synchrotron = inject("synchrotron"),
    xbpm_feedback: XBPMFeedback = inject("xbpm_feedback"),
    zebra: Zebra = inject("zebra"),
    zocalo: ZocaloResults = inject("zocalo"),
    smargon: Smargon = inject("smargon"),
):
    """Add a docstring"""
    # Composites have to be made this way until https://github.com/DiamondLightSource/dodal/issues/874
    # is done and we can properly use composite devices in BlueAPI
    composite = FlyScanXRayCentreComposite(
        attenuator,
        backlight,
        eiger,
        zebra_fast_grid_scan,
        synchrotron,
        xbpm_feedback,
        zebra,
        zocalo,
        smargon,
    )
    xrc_event_handler = XRayCentreEventHandler()

    @bpp.subs_decorator(xrc_event_handler)
    def flyscan_and_fetch_results() -> MsgGenerator:
        yield from ispyb_activation_wrapper(
            flyscan_xray_centre_no_move(composite, parameters), parameters
        )

    yield from flyscan_and_fetch_results()
    # other stuff goes here


def flyscan_xray_centre_no_move(
    composite: FlyScanXRayCentreComposite, parameters: SpecifiedThreeDGridScan
):
    composite.eiger.set_detector_parameters(parameters.detector_params)
    composite.zocalo.zocalo_environment = EnvironmentConstants.ZOCALO_ENV

    @bpp.set_run_key_decorator(PlanNameConstants.GRIDSCAN_OUTER)
    @bpp.run_decorator(  # attach experiment metadata to the start document
        md={
            "subplan_name": PlanNameConstants.GRIDSCAN_OUTER,
            "mx_bluesky_parameters": parameters.model_dump_json(),
            "activate_callbacks": [
                "GridscanNexusFileCallback",
            ],
        }
    )
    @bpp.finalize_decorator(lambda: tidy(composite))
    @transmission_and_xbpm_feedback_for_collection_decorator(
        composite.xbpm_feedback,
        composite.attenuator,
        parameters.transmission_frac,
    )
    def run_gridscan_and_fetch_results_and_tidy(
        fgs_composite: FlyScanXRayCentreComposite,
        params: SpecifiedThreeDGridScan,
    ) -> MsgGenerator:
        yield from run_gridscan_and_fetch_results(composite, parameters)

    yield from run_gridscan_and_fetch_results_and_tidy(composite, parameters)


@bpp.set_run_key_decorator(PlanNameConstants.GRIDSCAN_AND_MOVE)
@bpp.run_decorator(md={"subplan_name": PlanNameConstants.GRIDSCAN_AND_MOVE})
def run_gridscan_and_fetch_results(
    fgs_composite: FlyScanXRayCentreComposite,
    parameters: SpecifiedThreeDGridScan,
) -> MsgGenerator:
    """A multi-run plan which runs a gridscan, gets the results from zocalo
    and fires an event with the centres of mass determined by zocalo"""

    yield from setup_zebra_for_xrc_flyscan(fgs_composite.zebra, wait=True)

    LOGGER.info("Starting grid scan")
    yield from bps.stage(
        fgs_composite.zocalo, group=ZOCALO_STAGE_GROUP
    )  # connect to zocalo and make sure the queue is clear
    yield from run_gridscan(fgs_composite, parameters, feature_controlled)

    LOGGER.info("Grid scan finished, getting results.")

    try:
        with TRACER.start_span("wait_for_zocalo"):
            yield from bps.trigger_and_read(
                [fgs_composite.zocalo], name=ZOCALO_READING_PLAN_NAME
            )
            LOGGER.info("Zocalo triggered and read, interpreting results.")
            xrc_results = yield from get_full_processing_results(fgs_composite.zocalo)
            LOGGER.info(f"Got xray centres, top 5: {xrc_results[:5]}")
            filtered_results = [
                result
                for result in xrc_results
                if result["total_count"] >= ZOCALO_MIN_TOTAL_COUNT_THRESHOLD
            ]
            discarded_count = len(xrc_results) - len(filtered_results)
            if discarded_count > 0:
                LOGGER.info(
                    f"Removed {discarded_count} results because below threshold"
                )
            if filtered_results:
                flyscan_results = [
                    _xrc_result_in_boxes_to_result_in_mm(xr, parameters)
                    for xr in filtered_results
                ]
            else:
                LOGGER.warning("No X-ray centre received")
                raise CrystalNotFoundException()
            yield from _fire_xray_centre_result_event(flyscan_results)

    finally:
        # Turn off dev/shm streaming to avoid filling disk, see https://github.com/DiamondLightSource/hyperion/issues/1395
        LOGGER.info("Turning off Eiger dev/shm streaming")
        yield from bps.abs_set(fgs_composite.eiger.odin.fan.dev_shm_enable, 0)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809

        # Wait on everything before returning to GDA (particularly apertures), can be removed
        # when we do not return to GDA here
        yield from bps.wait()


def tidy(composite):
    # Do the Hyperion zebra flyscan tidy up
    pass
