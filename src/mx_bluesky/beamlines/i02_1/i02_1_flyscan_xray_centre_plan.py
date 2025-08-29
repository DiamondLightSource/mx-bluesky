from functools import partial

import bluesky.preprocessors as bpp
import pydantic
from bluesky.utils import MsgGenerator
from dodal.beamlines.i02_1 import ZebraFastGridScanTwoD
from dodal.common import inject
from dodal.devices.eiger import EigerDetector
from dodal.devices.fast_grid_scan import (
    set_fast_grid_scan_params as set_flyscan_params_plan,
)
from dodal.devices.i02_1.fast_grid_scan import ZebraGridScanParamsTwoD
from dodal.devices.i02_1.sample_motors import SampleMotors
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.zebra.zebra import Zebra

from mx_bluesky.beamlines.i02_1.device_setup_plans.setup_zebra import (
    setup_zebra_for_xrc_flyscan,
    tidy_up_zebra_after_gridscan,
)
from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    BeamlineSpecificFGSFeatures,
    FlyScanBaseComposite,
    common_flyscan_xray_centre,
    construct_beamline_specific_FGS_features,
)
from mx_bluesky.common.external_interaction.callbacks.common.callback_util import (
    create_gridscan_callbacks,
)
from mx_bluesky.common.parameters.device_composites import SampleStageWithOmega
from mx_bluesky.common.parameters.gridscan import SpecifiedThreeDGridScan
from mx_bluesky.common.utils.log import LOGGER


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class FlyScanXRayCentreComposite(
    FlyScanBaseComposite[ZebraGridScanParamsTwoD, SampleStageWithOmega]
):
    """All devices which are directly or indirectly required by this plan"""

    zebra: Zebra


def construct_i02_1_specific_features(
    fgs_composite: FlyScanXRayCentreComposite,
    parameters: SpecifiedThreeDGridScan,
) -> BeamlineSpecificFGSFeatures:
    signals_to_read_pre_flyscan = [
        fgs_composite.synchrotron.synchrotron_mode,
        fgs_composite.sample_stage,
    ]
    signals_to_read_during_collection = [
        fgs_composite.eiger.bit_depth,
    ]

    return construct_beamline_specific_FGS_features(
        _zebra_triggering_setup,
        partial(_tidy_plan, group="flyscan_zebra_tidy", wait=True),
        partial(
            set_flyscan_params_plan,
            fgs_composite.grid_scan,
            parameters.FGS_params,
        ),
        fgs_composite.grid_scan,
        signals_to_read_pre_flyscan,
        signals_to_read_during_collection,  # type: ignore # See : https://github.com/bluesky/bluesky/issues/1809
    )


def _zebra_triggering_setup(
    fgs_composite: FlyScanXRayCentreComposite,
):
    yield from setup_zebra_for_xrc_flyscan(fgs_composite.zebra)


def _tidy_plan(
    fgs_composite: FlyScanXRayCentreComposite, group, wait=True
) -> MsgGenerator:
    LOGGER.info("Tidying up Zebra")
    yield from tidy_up_zebra_after_gridscan(fgs_composite.zebra)


def i02_1_flyscan_xray_centre(
    parameters: SpecifiedThreeDGridScan,
    eiger: EigerDetector = inject("eiger"),
    zebra_fast_grid_scan: ZebraFastGridScanTwoD = inject("ZebraFastGridScanTwoD"),
    synchrotron: Synchrotron = inject("synchrotron"),
    zebra: Zebra = inject("zebra"),
    sample_motors: SampleMotors = inject("sample_motors"),
) -> MsgGenerator:
    """BlueAPI entry point for XRC grid scans"""

    # Composites have to be made this way until https://github.com/DiamondLightSource/dodal/issues/874
    # is done and we can properly use composite devices in BlueAPI
    composite = FlyScanXRayCentreComposite(
        eiger,
        synchrotron,
        sample_motors,
        zebra_fast_grid_scan,
        zebra,
    )

    beamline_specific = construct_i02_1_specific_features(composite, parameters)

    @bpp.subs_decorator(create_gridscan_callbacks())
    def decorated_flyscan_plan():
        yield from common_flyscan_xray_centre(composite, parameters, beamline_specific)

    yield from decorated_flyscan_plan()
