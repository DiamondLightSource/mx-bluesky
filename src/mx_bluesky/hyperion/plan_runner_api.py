import uvicorn
from fastapi import FastAPI

from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.plan_runner import PlanRunner

app = FastAPI()


# Ignore this function for code coverage as there is no way to shut down
# a server once it is started.
def create_server_for_udc(
    runner: PlanRunner, port: int
) -> uvicorn.Server:  # pragma: no cover
    # register resources with the app via instantiation
    StatusResource(runner)
    CallbackLiveness(runner)

    """Create a minimal API for Hyperion UDC mode"""
    config = uvicorn.Config("mx_bluesky.hyperion.plan_runner_api:app", port=port)
    server = uvicorn.Server(config)
    server.run()
    # app = create_app_for_udc(runner)
    #
    # flask_thread = Thread(
    #     target=app.run,
    #     kwargs={"host": "0.0.0.0", "port": port},
    #     daemon=True,
    # )
    # flask_thread.start()
    LOGGER.info(f"Hyperion now listening on {port}")
    return server


# def create_app_for_udc(runner: PlanRunner):
#     app = Flask(__name__)
#     api = Api(app)
#     api.add_resource(StatusResource, "/status", resource_class_args=[runner])
#     api.add_resource(CallbackLiveness, "/callbackPing", resource_class_args=[runner])
#     return app


class StatusResource:
    """Status endpoint, used by k8s healthcheck probe"""

    def __init__(self, runner: PlanRunner):
        super().__init__()
        self._runner = runner

    @app.get("/status")
    async def get(self):
        status = self._runner.current_status
        return {"status": status.value}


class CallbackLiveness:
    """Called periodically by the external callbacks to indicate that they are still running"""

    def __init__(self, runner: PlanRunner):
        super().__init__()
        self._runner = runner

    @app.get("/callbackPing")
    async def get(self):
        LOGGER.debug("External callback ping received.")
        self._runner.reset_callback_watchdog_timer()
