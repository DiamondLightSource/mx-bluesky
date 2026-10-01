from __future__ import annotations

from typing import Any

from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.common_dcm import DoubleCrystalMonochromator
from dodal.devices.eiger import EigerDetector
from dodal.devices.flux import Flux
from dodal.devices.slits import MinimalSlits
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.undulator import UndulatorInKeV

from mx_bluesky.common.device_setup_plans.beamsize.beamsize import (
    BeamSizePlans,
    TBeamSizeComposite,
)
from mx_bluesky.common.device_setup_plans.detector.beamline_specific import (
    BeamlineSpecificDetectorFeatures,
)
from mx_bluesky.common.device_setup_plans.gridscan.beamline_specific import (
    read_hardware_plan,
)
from mx_bluesky.common.parameters.constants import (
    DocDescriptorNames,
)
from mx_bluesky.common.utils.log import LOGGER


def read_hardware_for_zocalo(beamline_specific: BeamlineSpecificDetectorFeatures):
    """
    If the RunEngine is subscribed to the ZocaloCallback, this plan will also trigger zocalo.
    """
    yield from read_hardware_plan(
        beamline_specific.detector_zocalo_hw_read_signals,  # type: ignore
        DocDescriptorNames.ZOCALO_HW_READ,
    )


def standard_read_hardware_pre_collection(
    undulator: UndulatorInKeV,
    synchrotron: Synchrotron,
    s4_slit_gaps: MinimalSlits,
    dcm: DoubleCrystalMonochromator,
    smargon: Smargon,
):
    LOGGER.info("Reading status of beamline for callbacks, pre collection.")
    signals_to_read_pre_flyscan = [
        undulator.current_gap,
        synchrotron.synchrotron_mode,
        s4_slit_gaps,
        smargon,
        dcm.energy_in_keV,
    ]
    yield from read_hardware_plan(
        signals_to_read_pre_flyscan, DocDescriptorNames.HARDWARE_READ_PRE
    )


def standard_read_hardware_during_collection(
    beamsize_plans: BeamSizePlans[TBeamSizeComposite, Any],
    beamsize_devices: TBeamSizeComposite,
    attenuator: BinaryFilterAttenuator,
    flux: Flux,
    dcm: DoubleCrystalMonochromator,
    detector: EigerDetector,
):
    signals_to_read_during_collection = [
        attenuator.actual_transmission,
        flux.flux_reading,
        dcm.energy_in_keV,
        detector.bit_depth,
        detector.cam.roi_mode,
        detector.ispyb_detector_id,
    ]
    signals_to_read_during_collection += (
        beamsize_plans.signals_to_read_during_collection(beamsize_devices)
    )
    yield from read_hardware_plan(
        signals_to_read_during_collection,  # type: ignore # until https://github.com/DiamondLightSource/mx-bluesky/issues/1076
        DocDescriptorNames.HARDWARE_READ_DURING,
    )
