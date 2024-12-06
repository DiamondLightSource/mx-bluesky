"""Plan that comprises:
* Disable feedback
* Set undulator energy to the requested amount
* Adjust DCM and mirrors for the new energy
* reenable feedback
"""

import pydantic
from bluesky import plan_stubs as bps
from dodal.devices.attenuator import Attenuator
from dodal.devices.dcm import DCM
from dodal.devices.focusing_mirror import FocusingMirrorWithStripes, MirrorVoltages
from dodal.devices.undulator_dcm import UndulatorDCM
from dodal.devices.xbpm_feedback import XBPMFeedback

from mx_bluesky.hyperion.device_setup_plans import dcm_pitch_roll_mirror_adjuster
from mx_bluesky.hyperion.device_setup_plans.xbpm_feedback import (
    transmission_and_xbpm_feedback_for_collection_wrapper,
)

DESIRED_TRANSMISSION_FRACTION = 0.1

UNDULATOR_GROUP = "UNDULATOR_GROUP"


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class SetEnergyComposite:
    vfm: FocusingMirrorWithStripes
    mirror_voltages: MirrorVoltages
    dcm: DCM
    undulator_dcm: UndulatorDCM
    xbpm_feedback: XBPMFeedback
    attenuator: Attenuator


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
    if energy_ev:
        yield from transmission_and_xbpm_feedback_for_collection_wrapper(
            _set_energy_plan(energy_ev / 1000, composite),
            composite.xbpm_feedback,
            composite.attenuator,
            DESIRED_TRANSMISSION_FRACTION,
        )
