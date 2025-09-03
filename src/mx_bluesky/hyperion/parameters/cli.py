import argparse
from enum import StrEnum

from pydantic.dataclasses import dataclass

from mx_bluesky._version import version


class HyperionMode(StrEnum):
    GDA = "gda"
    UDC = "udc"


@dataclass
class HyperionArgs:
    mode: HyperionMode
    dev_mode: bool = False


def _add_callback_relevant_args(parser: argparse.ArgumentParser) -> None:
    """adds arguments relevant to hyperion-callbacks."""
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Use dev options, such as local graylog instances",
    )


def parse_callback_dev_mode_arg() -> bool:
    """Returns the bool representing the 'dev_mode' argument."""
    parser = argparse.ArgumentParser()
    _add_callback_relevant_args(parser)
    args = parser.parse_args()
    return args.dev


def parse_cli_args() -> HyperionArgs:
    """Parses all arguments relevant to hyperion.
    Returns:
         an HyperionArgs dataclass with the fields: (dev_mode: bool)"""
    parser = argparse.ArgumentParser()
    _add_callback_relevant_args(parser)
    parser.add_argument(
        "--version",
        help="Print hyperion version string",
        action="version",
        version=version,
    )
    parser.add_argument(
        "--mode",
        help="Launch in the specified mode (default is 'gda')",
        default=HyperionMode.GDA,
        type=HyperionMode,
        choices=HyperionMode.__members__.values(),
    )
    args = parser.parse_args()
    return HyperionArgs(dev_mode=args.dev or False, mode=args.mode)
