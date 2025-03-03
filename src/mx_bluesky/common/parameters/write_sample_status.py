from mx_bluesky.common.parameters.components import (
    MxBlueskyParameters,
    WithSample,
    WithVisit,
)

"""These two parameter classes can be removed once we remove the Hyperion entry points for the write sample status plans. See https://github.com/DiamondLightSource/mx-bluesky/issues/880"""


class WriteSampleStatus(MxBlueskyParameters, WithSample, WithVisit):
    exception_type: str
    visit: str = "Null"  # Unused field


class WriteSampleLoaded(MxBlueskyParameters, WithSample, WithVisit):
    visit: str = "Null"  # Unused field
