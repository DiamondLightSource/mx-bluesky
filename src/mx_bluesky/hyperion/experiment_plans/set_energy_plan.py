"""Plan that comprises:
* Disable feedback
* Set undulator energy to the requested amount
* Adjust DCM and mirrors for the new energy
* reenable feedback
"""

import bluesky.preprocessors as bpp
import pydantic
from bluesky import plan_stubs as bps
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.focusing_mirror import FocusingMirrorWithStripes, MirrorVoltages
from dodal.devices.i03.dcm import DCM
from dodal.devices.i03.undulator_dcm import UndulatorDCM
from dodal.devices.undulator import Undulator
from dodal.devices.xbpm_feedback import XBPMFeedback

from mx_bluesky.common.parameters.constants import PlanNameConstants
from mx_bluesky.common.preprocessors.preprocessors import (
    transmission_and_xbpm_feedback_for_collection_wrapper,
)
from mx_bluesky.hyperion.device_setup_plans import dcm_pitch_roll_mirror_adjuster

DESIRED_TRANSMISSION_FRACTION = 0.1

UNDULATOR_GROUP = "UNDULATOR_GROUP"


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class SetEnergyComposite:
    vfm: FocusingMirrorWithStripes
    mirror_voltages: MirrorVoltages
    dcm: DCM
    undulator_dcm: UndulatorDCM
    xbpm_feedback: XBPMFeedback
    attenuator: BinaryFilterAttenuator


# Remove composite after https://github.com/DiamondLightSource/dodal/issues/1092
@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class XBPMWrapperComposite:
    undulator: Undulator
    xbpm_feedback: XBPMFeedback
    attenuator: BinaryFilterAttenuator
    dcm: DCM


@bpp.set_run_key_decorator(PlanNameConstants.SET_ENERGY)
@bpp.run_decorator()
def _set_energy_plan(
    energy_kev,
    composite: SetEnergyComposite,
):
    yield from bps.abs_set(composite.undulator_dcm, energy_kev, group=UNDULATOR_GROUP)
    yield from dcm_pitch_roll_mirror_adjuster.adjust_dcm_pitch_roll_vfm_from_lut(
        composite.undulator_dcm,
        composite.vfm,
        composite.mirror_voltages,
        energy_kev,
    )
    yield from bps.wait(group=UNDULATOR_GROUP)


def set_energy_plan(
    energy_ev: float | None,
    composite: SetEnergyComposite,
):
    # Remove conversion after https://github.com/DiamondLightSource/dodal/issues/1092
    composite_for_wrapper = XBPMWrapperComposite(
        composite.undulator_dcm.undulator_ref._obj,  # noqa: SLF001
        composite.xbpm_feedback,
        composite.attenuator,
        composite.dcm,
    )

    if energy_ev:
        yield from transmission_and_xbpm_feedback_for_collection_wrapper(
            _set_energy_plan(energy_ev / 1000, composite),
            composite_for_wrapper,
            DESIRED_TRANSMISSION_FRACTION,
        )
