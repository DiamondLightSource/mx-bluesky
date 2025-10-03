import pydantic
from dodal.devices.i04.transfocator import Transfocator

from mx_bluesky.common.parameters.device_composites import (
    GridDetectThenXRayCentreComposite,
)


@pydantic.dataclasses.dataclass(config={"arbitrary_types_allowed": True})
class I04GridDetectThenXRayCentreComposite(GridDetectThenXRayCentreComposite):
    """
    The transofcator is specific to i04 and is used instead of the aperture to change
    beamsize.
    """

    transfocator: Transfocator
