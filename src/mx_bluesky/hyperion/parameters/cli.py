import argparse

from pydantic.dataclasses import dataclass

from mx_bluesky._version import version


@dataclass
class HyperionArgs:
    dev_mode: bool = False
    verbose_event_logging: bool = False


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
    """Parses all arguments relevant to hyperion. Returns an HyperionArgs dataclass with
    the fields: (verbose_event_logging: bool,
                 dev_mode: bool)"""
    parser = argparse.ArgumentParser()
    _add_callback_relevant_args(parser)
    parser.add_argument(
        "--verbose-event-logging",
        action="store_true",
        help="Log all bluesky event documents to graylog",
    )
    parser.add_argument(
        "--version",
        help="Print hyperion version string",
        action="version",
        version=version,
    )
    args = parser.parse_args()
    return HyperionArgs(
        verbose_event_logging=args.verbose_event_logging or False,
        dev_mode=args.dev or False,
    )
