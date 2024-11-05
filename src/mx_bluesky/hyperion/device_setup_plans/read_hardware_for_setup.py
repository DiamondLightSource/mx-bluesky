from __future__ import annotations

import bluesky.plan_stubs as bps
from dodal.devices.aperturescatterguard import ApertureScatterguard
from dodal.devices.attenuator import Attenuator
from dodal.devices.dcm import DCM
from dodal.devices.eiger import EigerDetector
from dodal.devices.flux import Flux
from dodal.devices.s4_slit_gaps import S4SlitGaps
from dodal.devices.smargon import Smargon
from dodal.devices.synchrotron import Synchrotron
from dodal.devices.undulator import Undulator

from mx_bluesky.hyperion.log import LOGGER
from mx_bluesky.hyperion.parameters.constants import CONST


def read_hardware_pre_collection(
    undulator: Undulator,
    synchrotron: Synchrotron,
    s4_slit_gaps: S4SlitGaps,
    dcm: DCM,
    smargon: Smargon,
):
    LOGGER.info("Reading status of beamline for callbacks, pre collection.")
    yield from bps.create(
        name=CONST.DESCRIPTORS.HARDWARE_READ_PRE
    )  # gives name to event *descriptor* document
    yield from bps.read(undulator.current_gap)
    yield from bps.read(synchrotron.synchrotron_mode)
    yield from bps.read(s4_slit_gaps.xgap)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from bps.read(s4_slit_gaps.ygap)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from bps.read(smargon.x)
    yield from bps.read(smargon.y)
    yield from bps.read(smargon.z)
    yield from bps.read(dcm.energy_in_kev)
    yield from bps.save()


def read_hardware_during_collection(
    aperture_scatterguard: ApertureScatterguard,
    attenuator: Attenuator,
    flux: Flux,
    dcm: DCM,
    detector: EigerDetector,
):
    LOGGER.info("Reading status of beamline for callbacks, during collection.")
    yield from bps.create(name=CONST.DESCRIPTORS.HARDWARE_READ_DURING)
    yield from bps.read(aperture_scatterguard)
    yield from bps.read(attenuator.actual_transmission)
    yield from bps.read(flux.flux_reading)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from bps.read(dcm.energy_in_kev)
    yield from bps.read(detector.bit_depth)  # type: ignore # See: https://github.com/bluesky/bluesky/issues/1809
    yield from bps.save()
