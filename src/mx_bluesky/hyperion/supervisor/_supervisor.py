from importlib import resources

from blueapi.config import ApplicationConfig
from blueapi.core import BlueskyContext

from mx_bluesky.hyperion.runner import BaseRunner


def create_context() -> BlueskyContext:
    config_json = resources.read_text(
        "mx_bluesky.hyperion.supervisor", "supervisor_config.yaml"
    )
    app_config = ApplicationConfig.model_validate_json(config_json)
    context = BlueskyContext(configuration=app_config)
    return context


class SupervisorRunner(BaseRunner):
    """Runner that executes plans by delegating to a remote blueapi instance"""

    def shutdown(self):
        pass
