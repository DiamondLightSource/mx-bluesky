from pydantic import Field

from mx_bluesky.common.parameters.components import (
    WithSample,
    WithSnapshots.
    WithVisit,
)


class AithreRobotLoad(
    WithSample, WithSnapshots, WithVisit,
)
