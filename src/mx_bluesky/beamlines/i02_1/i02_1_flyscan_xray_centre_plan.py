from functools import partial

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import pydantic
from bluesky.utils import MsgGenerator
from dodal.common import inject
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import ZebraFastGridScan
from dodal.devices.fast_grid_scan import (
    set_fast_grid_scan_params as set_flyscan_params_plan,
)
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zocalo.zocalo_results import (
    ZocaloResults,
)

from mx_bluesky.beamlines.i02_1.constants import I02_1_Constants
from mx_bluesky.beamlines.i02_1.device_setup_plans.setup_zebra import (
    setup_zebra_for_xrc_flyscan,
    tidy_up_zebra_after_gridscan,
)
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
from mx_bluesky.common.plans.common_flyscan_xray_centre_plan import (
    CALLBACKS_FOR_SUBS_DECORATOR,
    BeamlineSpecificFGSFeatures,
    FlyScanEssentialDevices,
    common_flyscan_xray_centre,
    construct_beamline_specific_FGS_features,
)
from mx_bluesky.common.utils.log import LOGGER, do_default_logging_setup


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class FlyScanXRayCentreComposite(FlyScanEssentialDevices):
    """All devices which are directly or indirectly required by this plan"""

    @property
    def sample_motors(self) -> Smargon:
        """Convenience alias with a more user-friendly name"""
        return self.smargon


def construct_i02_1_specific_features(
    fgs_composite: FlyScanXRayCentreComposite,
    parameters: SpecifiedThreeDGridScan,
) -> BeamlineSpecificFGSFeatures:
    signals_to_read_pre_flyscan = [
        fgs_composite.synchrotron.synchrotron_mode,
        fgs_composite.smargon,
    ]
    signals_to_read_during_collection = [
        fgs_composite.eiger.bit_depth,
    ]

    return construct_beamline_specific_FGS_features(
        _zebra_triggering_setup,
        partial(_tidy_plan, group="flyscan_zebra_tidy", wait=True),
        partial(
            set_flyscan_params_plan,
            fgs_composite.zebra_fast_grid_scan,
            parameters.FGS_params,
        ),
        fgs_composite.zebra_fast_grid_scan,
        signals_to_read_pre_flyscan,
        signals_to_read_during_collection,  # type: ignore # See : https://github.com/bluesky/bluesky/issues/1809
    )


def _zebra_triggering_setup(
    fgs_composite: FlyScanXRayCentreComposite,
    parameters: SpecifiedThreeDGridScan,
):
    yield from setup_zebra_for_xrc_flyscan(fgs_composite.zebra)


def _tidy_plan(
    fgs_composite: FlyScanXRayCentreComposite, group, wait=True
) -> MsgGenerator:
    LOGGER.info("Tidying up Zebra")
    yield from tidy_up_zebra_after_gridscan(fgs_composite.zebra)
    LOGGER.info("Tidying up Zocalo")
    # make sure we don't consume any other results
    yield from bps.unstage(fgs_composite.zocalo, group=group, wait=wait)


def i02_1_flyscan_xray_centre(
    parameters: SpecifiedThreeDGridScan,
    eiger: EigerDetector = inject("eiger"),
    zebra_fast_grid_scan: ZebraFastGridScan = inject("zebra_fast_grid_scan"),
    synchrotron: Synchrotron = inject("synchrotron"),
    zebra: Zebra = inject("zebra"),
    zocalo: ZocaloResults = inject("zocalo"),
    smargon: Smargon = inject("smargon"),
) -> MsgGenerator:
    """BlueAPI entry point for XRC grid scans"""

    do_default_logging_setup(
        I02_1_Constants.LOG_FILE_NAME,
        I02_1_Constants.GRAYLOG_PORT,
    )

    # Composites have to be made this way until https://github.com/DiamondLightSource/dodal/issues/874
    # is done and we can properly use composite devices in BlueAPI
    composite = FlyScanXRayCentreComposite(
        eiger,
        zebra_fast_grid_scan,
        synchrotron,
        zebra,
        zocalo,
        smargon,
    )

    beamline_specific = construct_i02_1_specific_features(composite, parameters)

    @bpp.subs_decorator(CALLBACKS_FOR_SUBS_DECORATOR)
    def decorated_flyscan_plan():
        yield from common_flyscan_xray_centre(composite, parameters, beamline_specific)

    yield from decorated_flyscan_plan()
