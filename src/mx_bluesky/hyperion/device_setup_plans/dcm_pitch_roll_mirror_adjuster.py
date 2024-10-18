import json

import bluesky.plan_stubs as bps
from dodal.devices.focusing_mirror import (
    FocusingMirrorWithStripes,
    MirrorStripe,
    MirrorVoltages,
)
from dodal.devices.undulator_dcm import UndulatorDCM
from dodal.devices.util.adjuster_plans import lookup_table_adjuster
from dodal.devices.util.bragg_angle import energy_to_bragg_angle
from dodal.devices.util.lookup_tables import (
    linear_interpolation_lut,
)

from mx_bluesky.hyperion.log import LOGGER

MIRROR_VOLTAGE_GROUP = "MIRROR_VOLTAGE_GROUP"
DCM_GROUP = "DCM_GROUP"


def _apply_and_wait_for_voltages_to_settle(
    stripe: MirrorStripe,
    mirror_voltages: MirrorVoltages,
):
    with open(mirror_voltages.voltage_lookup_table_path) as lut_file:
        json_obj = json.load(lut_file)

    # sample mode is the only mode supported
    sample_data = json_obj["sample"]
    if stripe == MirrorStripe.BARE:
        stripe_key = "bare"
    elif stripe == MirrorStripe.RHODIUM:
        stripe_key = "rh"
    elif stripe == MirrorStripe.PLATINUM:
        stripe_key = "pt"

    for mirror_key, channels in {
        "hfm": mirror_voltages.horizontal_voltages,
        "vfm": mirror_voltages.vertical_voltages,
    }.items():
        required_voltages = sample_data[stripe_key][mirror_key]

        for voltage_channel, required_voltage in zip(
            channels.values(), required_voltages, strict=True
        ):
            LOGGER.debug(
                f"Applying and waiting for voltage {voltage_channel.name} = {required_voltage}"
            )
            yield from bps.abs_set(
                voltage_channel, required_voltage, group=MIRROR_VOLTAGE_GROUP
            )

    yield from bps.wait(group=MIRROR_VOLTAGE_GROUP)


def adjust_mirror_stripe(
    energy_kev, mirror: FocusingMirrorWithStripes, mirror_voltages: MirrorVoltages
):
    """Feedback should be OFF prior to entry, in order to prevent
    feedback from making unnecessary corrections while beam is being adjusted."""
    stripe = mirror.energy_to_stripe(energy_kev)

    LOGGER.info(
        f"Adjusting mirror stripe for {energy_kev}keV selecting {stripe} stripe"
    )
    yield from bps.abs_set(mirror.stripe, stripe, wait=True)
    yield from bps.trigger(mirror.apply_stripe)

    LOGGER.info("Adjusting mirror voltages...")
    yield from _apply_and_wait_for_voltages_to_settle(stripe, mirror_voltages)


def adjust_dcm_pitch_roll_vfm_from_lut(
    undulator_dcm: UndulatorDCM,
    vfm: FocusingMirrorWithStripes,
    mirror_voltages: MirrorVoltages,
    energy_kev,
):
    """Beamline energy-change post-adjustments : Adjust DCM and VFM directly from lookup tables.
    Lookups are performed against the Bragg angle which is computed directly from the target energy
    rather than waiting for the EPICS controls PV to reach it.
    Feedback should be OFF prior to entry, in order to prevent
    feedback from making unnecessary corrections while beam is being adjusted."""

    # Adjust DCM Pitch
    dcm = undulator_dcm.dcm
    LOGGER.info(f"Adjusting DCM and VFM for {energy_kev} keV")
    bragg_deg = energy_to_bragg_angle(energy_kev)
    LOGGER.info(f"Target Bragg angle = {bragg_deg} degrees")
    dcm_pitch_adjuster = lookup_table_adjuster(
        linear_interpolation_lut(undulator_dcm.pitch_energy_table_path),
        dcm.pitch_in_mrad,
        bragg_deg,
    )
    yield from dcm_pitch_adjuster(DCM_GROUP)
    # It's possible we can remove these waits but we need to check
    LOGGER.info("Waiting for DCM pitch adjust to complete...")

    # DCM Roll
    dcm_roll_adjuster = lookup_table_adjuster(
        linear_interpolation_lut(undulator_dcm.roll_energy_table_path),
        dcm.roll_in_mrad,
        bragg_deg,
    )
    yield from dcm_roll_adjuster(DCM_GROUP)
    LOGGER.info("Waiting for DCM roll adjust to complete...")

    # DCM Perp pitch
    offset_mm = undulator_dcm.dcm_fixed_offset_mm
    LOGGER.info(f"Adjusting DCM offset to {offset_mm} mm")
    yield from bps.abs_set(dcm.offset_in_mm, offset_mm, group=DCM_GROUP)

    #
    # Adjust mirrors
    #

    # No need to change HFM

    # Assumption is focus mode is already set to "sample"
    # not sure how we check this

    # VFM Stripe selection
    yield from adjust_mirror_stripe(energy_kev, vfm, mirror_voltages)
    yield from bps.wait(DCM_GROUP)

    # VFM Adjust - for I03 this table always returns the same value
    vfm_lut = vfm.bragg_to_lat_lookup_table_path
    assert vfm_lut is not None
    vfm_x_adjuster = lookup_table_adjuster(
        linear_interpolation_lut(vfm_lut),
        vfm.x_mm,
        bragg_deg,
    )
    LOGGER.info("Waiting for VFM Lat (Horizontal Translation) to complete...")
    yield from vfm_x_adjuster()
