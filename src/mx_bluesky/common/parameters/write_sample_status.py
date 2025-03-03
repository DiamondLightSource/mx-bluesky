from mx_bluesky.common.parameters.components import (
    MxBlueskyParameters,
    WithSample,
    WithVisit,
)


class WriteSampleStatus(MxBlueskyParameters, WithSample, WithVisit):
    exception_type: str
    visit: str = ""


class WriteSampleLoaded(MxBlueskyParameters, WithSample, WithVisit):
    visit: str = ""
