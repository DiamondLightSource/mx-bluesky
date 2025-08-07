import json
import threading
from dataclasses import asdict
from sys import argv
from traceback import format_exception

from blueapi.core import BlueskyContext
from flask import Flask, request
from flask_restful import Api, Resource

from mx_bluesky.common.external_interaction import alerting
from mx_bluesky.common.external_interaction.alerting.log_based_service import (
    LoggingAlertService,
)
from mx_bluesky.common.parameters.constants import Actions, Status
from mx_bluesky.common.utils.log import (
    LOGGER,
    do_default_logging_setup,
    flush_debug_handler,
)
from mx_bluesky.hyperion.baton_handler import run_forever
from mx_bluesky.hyperion.experiment_plans.experiment_registry import (
    PLAN_REGISTRY,
    PlanNotFound,
)
from mx_bluesky.hyperion.external_interaction.agamemnon import (
    compare_params,
    update_params_from_agamemnon,
)
from mx_bluesky.hyperion.parameters.cli import (
    HyperionArgs,
    HyperionMode,
    parse_cli_args,
)
from mx_bluesky.hyperion.parameters.constants import CONST, HyperionConstants
from mx_bluesky.hyperion.parameters.load_centre_collect import LoadCentreCollect
from mx_bluesky.hyperion.plan_runner import PlanRunner
from mx_bluesky.hyperion.plan_runner_api import create_server_for_udc
from mx_bluesky.hyperion.runner import (
    GDARunner,
    StatusAndMessage,
    make_error_status_and_message,
)
from mx_bluesky.hyperion.utils.context import setup_context


def compose_start_args(context: BlueskyContext, plan_name: str, action: Actions):
    experiment_registry_entry = PLAN_REGISTRY.get(plan_name)
    if experiment_registry_entry is None:
        raise PlanNotFound(f"Experiment plan '{plan_name}' not found in registry.")

    experiment_internal_param_type = experiment_registry_entry.get("param_type")
    plan = context.plan_functions.get(plan_name)
    if experiment_internal_param_type is None:
        raise PlanNotFound(
            f"Corresponding internal param type for '{plan_name}' not found in registry."
        )
    if plan is None:
        raise PlanNotFound(
            f"Experiment plan '{plan_name}' not found in context. Context has {context.plan_functions.keys()}"
        )
    try:
        parameters = experiment_internal_param_type(**json.loads(request.data))
        parameters = update_params_from_agamemnon(parameters)
        if isinstance(parameters, LoadCentreCollect):
            compare_params(parameters)
        if parameters.model_extra:
            raise ValueError(f"Extra fields not allowed {parameters.model_extra}")
    except Exception as e:
        raise ValueError(
            f"Supplied parameters don't match the plan for this endpoint {request.data}, for plan {plan_name}"
        ) from e
    return plan, parameters, plan_name


class RunExperiment(Resource):
    def __init__(self, runner: GDARunner, context: BlueskyContext) -> None:
        super().__init__()
        self.runner = runner
        self.context = context

    def put(self, plan_name: str, action: Actions):
        status_and_message = StatusAndMessage(Status.FAILED, f"{action} not understood")
        if action == Actions.START.value:
            try:
                plan, params, plan_name = compose_start_args(
                    self.context, plan_name, action
                )
                status_and_message = self.runner.start(plan, params, plan_name)
            except Exception as e:
                status_and_message = make_error_status_and_message(e)
                LOGGER.error("".join(format_exception(e)))

        elif action == Actions.STOP.value:
            status_and_message = self.runner.stop()
        # no idea why mypy gives an attribute error here but nowhere else for this
        # exact same situation...
        return asdict(status_and_message)  # type: ignore


class StopOrStatus(Resource):
    def __init__(self, runner: GDARunner) -> None:
        super().__init__()
        self.runner: GDARunner = runner

    def put(self, action):
        status_and_message = StatusAndMessage(Status.FAILED, f"{action} not understood")
        if action == Actions.STOP.value:
            status_and_message = self.runner.stop()
        return asdict(status_and_message)

    def get(self, **kwargs):
        action = kwargs.get("action")
        status_and_message = StatusAndMessage(Status.FAILED, f"{action} not understood")
        if action == Actions.STATUS.value:
            LOGGER.debug(
                f"Runner received status request - state of the runner object is: {self.runner.__dict__} - state of the RE is: {self.runner.RE.__dict__}"
            )
            status_and_message = self.runner.current_status
        return asdict(status_and_message)


class FlushLogs(Resource):
    def put(self, **kwargs):
        try:
            log_file = flush_debug_handler()
            status_and_message = StatusAndMessage(
                Status.SUCCESS, f"Flushed debug log to {log_file}"
            )
        except Exception as e:
            status_and_message = StatusAndMessage(
                Status.FAILED, f"Failed to flush debug log: {e}"
            )
        return asdict(status_and_message)


def create_app(runner: GDARunner, test_config=None) -> Flask:
    app = Flask(__name__)
    if test_config:
        app.config.update(test_config)
    api = Api(app)

    api.add_resource(
        RunExperiment,
        "/<string:plan_name>/<string:action>",
        resource_class_args=[runner, runner.context],
    )

    api.add_resource(
        FlushLogs,
        "/flush_debug_log",
    )
    api.add_resource(
        StopOrStatus,
        "/<string:action>",
        resource_class_args=[runner],
    )
    return app


def initialise_globals(args: HyperionArgs):
    """Do all early main low-level application initialisation."""
    do_default_logging_setup(
        CONST.LOG_FILE_NAME, CONST.GRAYLOG_PORT, dev_mode=args.dev_mode
    )
    LOGGER.info(f"Hyperion launched with args:{argv}")
    alerting.set_alerting_service(LoggingAlertService(CONST.GRAYLOG_STREAM_ID))


def main():
    """Main application entry point."""
    args = parse_cli_args()
    initialise_globals(args)
    hyperion_port = HyperionConstants.HYPERION_PORT
    context = setup_context(dev_mode=args.dev_mode)

    if args.mode == HyperionMode.GDA:
        runner = GDARunner(context=context)
        app = create_app(runner)
        flask_thread = threading.Thread(
            target=lambda: app.run(
                host="0.0.0.0", port=hyperion_port, debug=True, use_reloader=False
            ),
            daemon=True,
        )
        flask_thread.start()
        LOGGER.info(
            f"Hyperion now listening on {hyperion_port} ({'IN DEV' if args.dev_mode else ''})"
        )
        runner.wait_on_queue()
    else:
        plan_runner = PlanRunner(context)
        create_server_for_udc(plan_runner)
        run_forever(plan_runner)


if __name__ == "__main__":
    main()
