from typing import Protocol, TypeVar

from bluesky.utils import MsgGenerator

TBeamSizeComposite = TypeVar("TBeamSizeComposite", contravariant=True)


class BeamSizePlans(Protocol[TBeamSizeComposite]):
    def make_safe_for_robot_load_plan(
        self, devices: TBeamSizeComposite, group: str
    ) -> MsgGenerator:
        """Execute any motions required to make safe for robot load
        Args:
            devices: composite containing any necessary beamsize devices
            group: Name of bluesky group which will be waited on prior to robot load"""
        ...
