from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI

from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.hyperion.plan_runner import PlanRunner

app = FastAPI()

_plan_runner: PlanRunner


# Ignore this function for code coverage as there is no way to shut down
# a server once it is started.
def create_server_for_udc(
    runner: PlanRunner, port: int
) -> uvicorn.Server:  # pragma: no cover
    # register resources with the app via instantiation
    global _plan_runner
    _plan_runner = runner

    """Create a minimal API for Hyperion UDC mode"""
    config = uvicorn.Config("mx_bluesky.hyperion.plan_runner_api:app", port=port)
    server = uvicorn.Server(config)
    server.run()

    LOGGER.info(f"Hyperion now listening on {port}")
    return server


def plan_runner() -> PlanRunner:
    return _plan_runner


@app.get("/status")
async def get_status(runner: Annotated[PlanRunner, Depends(plan_runner)]):
    status = runner.current_status
    return {"status": status.value}


@app.get("/callbackPing")
async def get_callback_ping(runner: Annotated[PlanRunner, Depends(plan_runner)]):
    LOGGER.debug("External callback ping received.")
    runner.reset_callback_watchdog_timer()
