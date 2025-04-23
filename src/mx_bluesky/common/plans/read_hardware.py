from __future__ import annotations

import bluesky.plan_stubs as bps
from bluesky.protocols import Readable
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.attenuator.attenuator import BinaryFilterAttenuator
from dodal.devices.common_dcm import BaseDCM
from dodal.devices.eiger import EigerDetector
from dodal.devices.flux import Flux
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.undulator import Undulator

from mx_bluesky.common.parameters.constants import (
    DocDescriptorNames,
)
from mx_bluesky.common.utils.log import LOGGER


def read_hardware_plan(
    signals: list[Readable],
    event_name: str,
):
    LOGGER.info(f"Reading status of beamline for event, {event_name}")
    yield from bps.create(name=event_name)
    for signal in signals:
        yield from bps.read(signal)
    yield from bps.save()


def read_hardware_for_zocalo(detector: EigerDetector):
    """ "
    If the RunEngine is subscribed to the ZocaloCallback, this plan will also trigger zocalo.
    """
    yield from read_hardware_plan(
        [detector.odin.file_writer.id],  # type: ignore
        DocDescriptorNames.ZOCALO_HW_READ,
    )


def standard_read_hardware_pre_collection(
    undulator: Undulator,
    synchrotron: Synchrotron,
    s4_slit_gaps: S4SlitGaps,
    dcm: BaseDCM,
    smargon: Smargon,
):
    LOGGER.info("Reading status of beamline for callbacks, pre collection.")
    signals_to_read_pre_flyscan = [
        undulator.current_gap,
        synchrotron.synchrotron_mode,
        s4_slit_gaps,
        smargon,
        dcm.energy_in_kev,
    ]
    yield from read_hardware_plan(
        signals_to_read_pre_flyscan, DocDescriptorNames.HARDWARE_READ_PRE
    )


def standard_read_hardware_during_collection(
    aperture_scatterguard: ApertureScatterguard,
    attenuator: BinaryFilterAttenuator,
    flux: Flux,
    dcm: BaseDCM,
    detector: EigerDetector,
):
    signals_to_read_during_collection = [
        aperture_scatterguard,
        attenuator.actual_transmission,
        flux.flux_reading,
        dcm.energy_in_kev,
        detector.bit_depth,
    ]
    yield from read_hardware_plan(
        signals_to_read_during_collection, DocDescriptorNames.HARDWARE_READ_DURING
    )
