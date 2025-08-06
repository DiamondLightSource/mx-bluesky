from threading import Thread

from flask import Flask
from flask_restful import Api, Resource

from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.parameters.constants import HyperionConstants
from mx_bluesky.hyperion.plan_runner import PlanRunner


# Ignore this function for code coverage as there is no way to shut down
# a server once it is started.
def create_server_for_udc(runner: PlanRunner) -> Thread:  # pragma: no cover
    """Create a minimal API for Hyperion UDC mode"""
    app = create_app_for_udc(runner)

    flask_thread = Thread(
        target=app.run,
        kwargs={"host": "0.0.0.0", "port": HyperionConstants.HYPERION_PORT},
        daemon=True,
    )
    flask_thread.start()
    LOGGER.info(f"Hyperion now listening on {HyperionConstants.HYPERION_PORT}")
    return flask_thread


def create_app_for_udc(runner):
    app = Flask(__name__)
    api = Api(app)
    api.add_resource(
        ShutdownResource,
        "/shutdown",
        resource_class_args=[runner],
    )
    api.add_resource(StatusResource, "/status", resource_class_args=[runner])
    return app


class ShutdownResource(Resource):
    """Shutdown endpoint, required for implementing hyperion_restart() functionality
    when running in a container."""

    def __init__(self, runner: PlanRunner):
        super().__init__()
        self._runner = runner

    def post(self):
        LOGGER.info("Received shutdown API request, sending shutdown.")
        self._runner.shutdown()


class StatusResource(Resource):
    """Status endpoint, used by k8s healthcheck probe"""

    def __init__(self, runner: PlanRunner):
        super().__init__()
        self._runner = runner

    def get(self):
        status = self._runner.current_status
        return {"status": status.value}
