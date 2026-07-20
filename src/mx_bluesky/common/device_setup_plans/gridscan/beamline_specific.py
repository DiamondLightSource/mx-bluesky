from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from functools import partial
from typing import Generic, TypeVar

from bluesky import plan_stubs as bps
from bluesky.protocols import Readable
from bluesky.utils import MsgGenerator
from dodal.devices.fast_grid_scan import FastGridScanCommon

from mx_bluesky.common.device_setup_plans.detector.beamline_specific import (
    BeamlineSpecificDetectorFeatures,
    TDiffractionEssentialDevices,
)
from mx_bluesky.common.parameters.components import DiffractionExperiment
from mx_bluesky.common.parameters.constants import DocDescriptorNames
from mx_bluesky.common.parameters.gridscan import GridScanParams
from mx_bluesky.common.utils.log import LOGGER

TSetupParameters = TypeVar(
    "TSetupParameters", bound=DiffractionExperiment, contravariant=True
)


@dataclasses.dataclass
class BeamlineSpecificFGSFeatures(
    BeamlineSpecificDetectorFeatures,
    Generic[TDiffractionEssentialDevices, TSetupParameters],
):
    setup_trigger_plan: Callable[
        [TDiffractionEssentialDevices, TSetupParameters, GridScanParams], MsgGenerator
    ]
    tidy_plan: Callable[[TDiffractionEssentialDevices], MsgGenerator]
    set_flyscan_params_plan: Callable[[GridScanParams], MsgGenerator]
    fgs_motors: FastGridScanCommon
    read_pre_flyscan_plan: Callable[
        ..., MsgGenerator
    ]  # Eventually replace with https://github.com/DiamondLightSource/mx-bluesky/issues/819
    read_during_collection_plan: Callable[..., MsgGenerator]


def construct_beamline_specific_fast_gridscan_features(
    detector_features: BeamlineSpecificDetectorFeatures[TDiffractionEssentialDevices],
    setup_trigger_plan: Callable[
        [TDiffractionEssentialDevices, TSetupParameters, GridScanParams], MsgGenerator
    ],
    tidy_plan: Callable[..., MsgGenerator],
    set_flyscan_params_plan: Callable[[GridScanParams], MsgGenerator],
    fgs_motors: FastGridScanCommon,
    signals_to_read_pre_flyscan: Sequence[Readable],
    signals_to_read_during_collection: Sequence[Readable],
) -> BeamlineSpecificFGSFeatures[TDiffractionEssentialDevices, TSetupParameters]:
    """Construct the class needed to do beamline-specific parts of the XRC FGS

    Args:
        detector_features: The features specific to setting up the detector
        setup_trigger_plan (Callable): Configure triggering, for example with the Zebra or PandA device.
        Ran directly before kicking off the gridscan.

        tidy_plan (Callable): Tidy up states of devices. Ran at the end of the flyscan, regardless of
        whether or not it finished successfully. Zocalo and Eiger are cleaned up separately

        set_flyscan_params_plan (Callable): Set PV's for the relevant Fast Grid Scan dodal device

        fgs_motors (Callable): Composite device representing the fast grid scan's motion program parameters.

        signals_to_read_pre_flyscan (Callable): Signals which will be read and saved as a bluesky event document
        after all configuration, but before the gridscan.

        signals_to_read_during_collection (Callable): Signals which will be read and saved as a bluesky event
        document whilst the gridscan motion is in progress

        detector_signals_to_read: The list of detector signals to read when generating callback events
    """
    read_pre_flyscan_plan = partial(
        read_hardware_plan,
        signals_to_read_pre_flyscan,
        DocDescriptorNames.HARDWARE_READ_PRE,
    )

    read_during_collection_plan = partial(
        read_hardware_plan,
        [
            *signals_to_read_during_collection,
            *detector_features.detector_hw_read_during_signals,
        ],
        DocDescriptorNames.HARDWARE_READ_DURING,
    )

    return BeamlineSpecificFGSFeatures(
        pre_arm_detector_plan=detector_features.pre_arm_detector_plan,
        arm_detector_plan=detector_features.arm_detector_plan,
        disarm_detector_plan=detector_features.disarm_detector_plan,
        tidy_detector_plan=detector_features.tidy_detector_plan,
        detector_zocalo_hw_read_signals=detector_features.detector_zocalo_hw_read_signals,
        detector_hw_read_during_signals=detector_features.detector_hw_read_during_signals,
        setup_trigger_plan=setup_trigger_plan,
        tidy_plan=tidy_plan,
        set_flyscan_params_plan=set_flyscan_params_plan,
        fgs_motors=fgs_motors,
        read_pre_flyscan_plan=read_pre_flyscan_plan,
        read_during_collection_plan=read_during_collection_plan,
    )


def read_hardware_plan(
    signals: Sequence[Readable],
    event_name: str,
):
    LOGGER.info(f"Reading status of beamline for event, {event_name}")
    yield from bps.create(name=event_name)
    for signal in signals:
        yield from bps.read(signal)
    yield from bps.save()
