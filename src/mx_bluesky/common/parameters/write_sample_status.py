from mx_bluesky.common.parameters.components import (
    MxBlueskyParameters,
    WithSample,
)


class WriteSampleStatus(MxBlueskyParameters, WithSample):
    exception_type: str


class WriteSampleLoaded(MxBlueskyParameters, WithSample): ...
