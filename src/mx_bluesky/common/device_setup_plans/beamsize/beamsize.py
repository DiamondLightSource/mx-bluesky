from collections.abc import Sequence
from typing import Protocol, TypeVar

from bluesky.utils import MsgGenerator

from mx_bluesky.common.parameters.components import AperturePolicy

TBeamSizeComposite = TypeVar("TBeamSizeComposite", contravariant=True)
TBeamSizeValue = TypeVar("TBeamSizeValue")


class BeamSizePlans(Protocol[TBeamSizeComposite, TBeamSizeValue]):  # type: ignore
    def make_safe_for_robot_load_plan(
        self, devices: TBeamSizeComposite, group: str
    ) -> MsgGenerator:
        """Execute any motions required to make safe for robot load
        Args:
            devices: composite containing any necessary beamsize devices
            group: Name of bluesky group which will be waited on prior to robot load"""
        ...

    def make_safe_for_oav(
        self, devices: TBeamSizeComposite, group: str
    ) -> MsgGenerator:
        """Execute any actions required to move beam size devices out of the way for the
        on-axis view when it is used
        Args:
            devices: composite containing any necessary beamsize devices
            group: Name of the bluesky group that the caller will wait on for completion
        """
        ...

    def prepare_beam_size(
        self, devices: TBeamSizeComposite, aperture_value: TBeamSizeValue, group: str
    ) -> MsgGenerator:
        """
        Execute any actions that can be performed early without conflicting with the beam.
        For example with the aperture-scatterguard, if it is already out-of-beam
        we can move slow axes early while the OAV is being used.
        Args:
            devices: The devices to use
            aperture_policy: Size of the aperture to use
            group: Name of the bluesky group that the caller will wait on for completion
        Returns:
            Generator that yields the plan steps
        """
        ...

    def perform_beam_size(
        self, devices: TBeamSizeComposite, aperture_value: TBeamSizeValue, group: str
    ) -> MsgGenerator:
        """
        Execute actions required to select the specified aperture, regardless of whether we called
        prepare first.
        Args:
            devices: The devices to use
            aperture_policy: Size of the aperture to use
            group: Name of the bluesky group that the caller will wait on for completion
        Returns:
            Generator that yields the plan steps
        """
        ...

    def beam_size_for_xrc(
        self, devices: TBeamSizeComposite, aperture_policy: AperturePolicy
    ) -> MsgGenerator[TBeamSizeValue]: ...

    def beam_size_for_rotation(
        self, devices: TBeamSizeComposite, aperture_policy: AperturePolicy
    ) -> MsgGenerator[TBeamSizeValue]: ...

    def signals_to_read_during_collection(
        self, devices: TBeamSizeComposite
    ) -> Sequence:
        """Obtain the list of signals to read during collection"""
        ...
