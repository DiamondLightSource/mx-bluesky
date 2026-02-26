import signal
from pathlib import Path
from sys import argv

from blueapi.config import ApplicationConfig, ConfigLoader
from blueapi.core import BlueskyContext

from mx_bluesky.common.external_interaction import alerting
from mx_bluesky.common.external_interaction.alerting.log_based_service import (
    LoggingAlertService,
)
from mx_bluesky.common.utils.log import (
    LOGGER,
    do_default_logging_setup,
)
from mx_bluesky.hyperion.baton_handler import run_forever
from mx_bluesky.hyperion.in_process_runner import InProcessRunner
from mx_bluesky.hyperion.parameters.cli import (
    HyperionArgs,
    HyperionMode,
    parse_cli_args,
)
from mx_bluesky.hyperion.parameters.constants import CONST, HyperionConstants
from mx_bluesky.hyperion.plan_runner import PlanRunner
from mx_bluesky.hyperion.plan_runner_api import create_server_for_udc
from mx_bluesky.hyperion.supervisor import SupervisorRunner
from mx_bluesky.hyperion.utils.context import setup_context


def initialise_globals(args: HyperionArgs):
    """Do all early main low-level application initialisation."""
    do_default_logging_setup(
        CONST.SUPERVISOR_LOG_FILE_NAME
        if args.mode == HyperionMode.SUPERVISOR
        else CONST.LOG_FILE_NAME,
        CONST.GRAYLOG_PORT,
        dev_mode=args.dev_mode,
    )
    LOGGER.info(f"Hyperion launched with args:{argv}")
    alerting.set_alerting_service(LoggingAlertService(CONST.GRAYLOG_STREAM_ID))


def main():
    """Main application entry point."""
    args = parse_cli_args()
    initialise_globals(args)

    match args.mode:
        case HyperionMode.UDC:
            context = setup_context(dev_mode=args.dev_mode)
            plan_runner = InProcessRunner(context, args.dev_mode)
        case HyperionMode.SUPERVISOR:
            if not args.client_config:
                raise RuntimeError(
                    "BlueAPI client configuration file must be specified in supervisor mode."
                )
            if not args.supervisor_config:
                raise RuntimeError(
                    "BlueAPI supervisor configuration file must be specified in supervisor mode."
                )

            client_config = _load_config_from_yaml(Path(args.client_config))
            supervisor_config = _load_config_from_yaml(Path(args.supervisor_config))
            context = BlueskyContext(configuration=supervisor_config)
            plan_runner = SupervisorRunner(context, client_config, args.dev_mode)
    create_server_for_udc(plan_runner, HyperionConstants.SUPERVISOR_PORT)
    _register_sigterm_handler(plan_runner)
    run_forever(plan_runner)


def _load_config_from_yaml(config_path: Path):
    loader = ConfigLoader(ApplicationConfig)
    loader.use_values_from_yaml(config_path)
    return loader.load()


def _register_sigterm_handler(runner: PlanRunner):
    def shutdown_on_sigterm(sig_num, frame):
        LOGGER.info("Received SIGTERM, shutting down...")
        runner.shutdown()

    signal.signal(signal.SIGTERM, shutdown_on_sigterm)


if __name__ == "__main__":
    main()
