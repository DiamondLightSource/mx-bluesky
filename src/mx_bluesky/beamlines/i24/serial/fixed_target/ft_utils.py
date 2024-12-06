"""
Define a mapping between the edm screens/IOC enum inputs for the general purpose PVs and
the map/chip/pump settings.
The enum values should not be changed unless they are also modified in the drop down
menu in the edm screen, as their order should always match.
New ones may be added if needed in the future.
"""

from enum import Enum, IntEnum


class MappingType(IntEnum):
    NoMap = 0
    Lite = 1

    def __str__(self) -> str:
        """Returns the mapping."""
        return self.name


# FIXME See https://github.com/DiamondLightSource/mx_bluesky/issues/77
class ChipType(IntEnum):
    Oxford = 0
    OxfordInner = 1
    Custom = 2
    Minichip = 3  # Mini oxford, 1 city block only
    MISP = 4  # New PSI polymer chip

    def __str__(self) -> str:
        """Returns the chip name."""
        return self.name


class PumpProbeSetting(IntEnum):
    NoPP = 0
    Short1 = 1
    Short2 = 2
    Repeat1 = 3
    Repeat2 = 4
    Repeat3 = 5
    Repeat5 = 6
    Repeat10 = 7
    Medium1 = 8

    def __str__(self) -> str:
        """Returns the pump-probe setting name."""
        return self.name


class Fiducials(str, Enum):
    origin = "origin"
    zero = "zero"
    fid1 = "f1"
    fid2 = "f2"
