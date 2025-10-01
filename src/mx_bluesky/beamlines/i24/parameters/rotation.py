from __future__ import annotations

from pydantic import field_validator
from sqlalchemy import Float

from mx_bluesky.common.parameters.rotation import SingleRotationScan


class MultiRotationScanByTransmissions(SingleRotationScan):
    transmission_fractions: list[Float]
    transmission_frac: float = -1

    @field_validator("transmission_frac")
    @classmethod
    def validate_transmission_frac(cls, val):
        if val != -1:
            raise ValueError(
                "The transmission_fractions field must be specified instead of the transmission_frac when using MultiRotationScanByTransmissions parameters"
            )
        return val
