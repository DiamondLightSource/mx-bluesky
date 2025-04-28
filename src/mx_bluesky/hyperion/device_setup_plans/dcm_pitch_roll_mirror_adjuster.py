import json

import bluesky.plan_stubs as bps
from dodal.devices.focusing_mirror import (
    FocusingMirrorWithStripes,
    MirrorStripe,
    MirrorVoltages,
)
from dodal.devices.i03.undulator_dcm import UndulatorDCM
from dodal.devices.util.adjuster_plans import lookup_table_adjuster
from dodal.devices.util.lookup_tables import (
    linear_interpolation_lut,
    parse_lookup_table,
)

from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.utils.utils import (
    energy_to_bragg_angle,
)

MIRROR_VOLTAGE_GROUP = "MIRROR_VOLTAGE_GROUP"
DCM_GROUP = "DCM_GROUP"
YAW_LAT_TIMEOUT_S = 30


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
            LOGGER.info(
                f"Applying and waiting for voltage {voltage_channel.name} = {required_voltage}"
            )
            yield from bps.abs_set(
                voltage_channel, required_voltage, group=MIRROR_VOLTAGE_GROUP, wait=True
            )


def adjust_mirror_stripe(
    energy_kev, mirror: FocusingMirrorWithStripes, mirror_voltages: MirrorVoltages
):
    """Feedback should be OFF prior to entry, in order to prevent
    feedback from making unnecessary corrections while beam is being adjusted."""
    mirror_config = mirror.energy_to_stripe(energy_kev)

    LOGGER.info(
        f"Adjusting mirror stripe for {energy_kev}keV selecting {mirror_config['stripe']} stripe"
    )
    yield from bps.abs_set(mirror.stripe, mirror_config["stripe"], wait=True)
    yield from bps.trigger(mirror.apply_stripe)

    # yaw, lat cannot be done simultaneously
    LOGGER.info(f"Adjusting {mirror.name} lat to {mirror_config['lat_mm']}")
    yield from bps.abs_set(
        mirror.x_mm, mirror_config["lat_mm"], wait=True, timeout=YAW_LAT_TIMEOUT_S
    )

    LOGGER.info(f"Adjusting {mirror.name} yaw to {mirror_config['yaw_mrad']}")
    yield from bps.abs_set(
        mirror.yaw_mrad, mirror_config["yaw_mrad"], wait=True, timeout=YAW_LAT_TIMEOUT_S
    )

    LOGGER.info("Adjusting mirror voltages...")
    yield from _apply_and_wait_for_voltages_to_settle(
        mirror_config["stripe"], mirror_voltages
    )


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
    dcm = undulator_dcm.dcm_ref()
    LOGGER.info(f"Adjusting DCM and VFM for {energy_kev} keV")
    d_spacing_a: float = yield from bps.rd(
        undulator_dcm.dcm_ref().crystal_metadata_d_spacing_a
    )
    bragg_deg = energy_to_bragg_angle(energy_kev, d_spacing_a)
    LOGGER.info(f"Target Bragg angle = {bragg_deg} degrees")
    dcm_pitch_adjuster = lookup_table_adjuster(
        linear_interpolation_lut(
            *parse_lookup_table(undulator_dcm.pitch_energy_table_path)
        ),
        dcm.xtal_1.pitch_in_mrad,
        bragg_deg,
    )
    yield from dcm_pitch_adjuster(DCM_GROUP)
    # It's possible we can remove these waits but we need to check
    LOGGER.info("Waiting for DCM pitch adjust to complete...")

    # DCM Roll
    dcm_roll_adjuster = lookup_table_adjuster(
        linear_interpolation_lut(
            *parse_lookup_table(undulator_dcm.roll_energy_table_path)
        ),
        dcm.xtal_1.roll_in_mrad,
        bragg_deg,
    )
    yield from dcm_roll_adjuster(DCM_GROUP)
    LOGGER.info("Waiting for DCM roll adjust to complete...")

    #
    # Adjust vfm mirror stripe and mirror voltages
    #

    # VFM Stripe selection
    yield from adjust_mirror_stripe(energy_kev, vfm, mirror_voltages)
