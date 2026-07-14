from __future__ import annotations

import pydantic
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.beamsize.beamsize import BeamsizeBase
from dodal.devices.common_dcm import DoubleCrystalMonochromator
from dodal.devices.fast_grid_scan import (
    PandAFastGridScan,
    ZebraFastGridScanThreeD,
)
from dodal.devices.flux import Flux
from dodal.devices.robot import BartRobot
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.undulator import UndulatorInKeV
from dodal.devices.xbpm_feedback import XBPMFeedback
from dodal.devices.zebra.zebra import Zebra
from dodal.devices.zebra.zebra_controlled_shutter import MXZebraShutter
from ophyd_async.fastcs.panda import HDFPanda

from mx_bluesky.common.parameters.device_composites import (
    GridDetectAndGridScanEssentialDevices,
)


# TODO move this out of this package https://github.com/DiamondLightSource/mx-bluesky/issues/1793
@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class HyperionGridDetectThenXRayCentreComposite(GridDetectAndGridScanEssentialDevices):
    """All devices which are directly or indirectly required by Hyperion Grid Detect and XRC plan"""

    attenuator: BinaryFilterAttenuator
    beamsize: BeamsizeBase
    dcm: DoubleCrystalMonochromator
    zebra_fast_grid_scan: ZebraFastGridScanThreeD
    flux: Flux
    s4_slit_gaps: S4SlitGaps
    undulator: UndulatorInKeV
    xbpm_feedback: XBPMFeedback
    zebra: Zebra
    robot: BartRobot
    sample_shutter: MXZebraShutter
    panda: HDFPanda
    panda_fast_grid_scan: PandAFastGridScan
