import argparse
from enum import StrEnum
from pathlib import Path

from pydantic.dataclasses import dataclass

from mx_bluesky._version import version
from mx_bluesky.hyperion.parameters.constants import HyperionConstants


class HyperionMode(StrEnum):
    GDA = "gda"
    UDC = "udc"
    SUPERVISOR = "supervisor"


@dataclass
class HyperionArgs:
    mode: HyperionMode
    dev_mode: bool = False
    client_config: str | None = None
    supervisor_config: str | None = None


@dataclass
class CallbackArgs:
    dev_mode: bool = False
    watchdog_port: int = HyperionConstants.HYPERION_PORT
    stomp_config: Path | None = None


def _add_callback_relevant_args(parser: argparse.ArgumentParser) -> None:
    """adds arguments relevant to hyperion-callbacks."""
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Use dev options, such as local graylog instances",
    )


def parse_callback_args() -> CallbackArgs:
    """Parse the CLI arguments for the watchdog port and dev mode into a CallbackArgs instance."""
    parser = argparse.ArgumentParser()
    _add_callback_relevant_args(parser)
    parser.add_argument(
        "--watchdog-port",
        type=int,
        help="Liveness port for callbacks to ping regularly",
    )
    parser.add_argument(
        "--stomp-config",
        type=Path,
        default=None,
        help="Specify config yaml for the STOMP backend (default is 0MQ)",
    )
    args = parser.parse_args()
    return CallbackArgs(
        dev_mode=args.dev,
        watchdog_port=args.watchdog_port,
        stomp_config=args.stomp_config,
    )


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
    parser.add_argument(
        "--client-config", help="Specify the blueapi client configuration file."
    )
    parser.add_argument(
        "--supervisor-config",
        help="Specify the supervisor bluesky context configuration file.",
    )
    args = parser.parse_args()
    return HyperionArgs(
        dev_mode=args.dev or False,
        mode=args.mode,
        supervisor_config=args.supervisor_config,
        client_config=args.client_config,
    )
