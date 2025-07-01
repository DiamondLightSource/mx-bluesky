import copy
import json
from datetime import timedelta
from typing import TypedDict

from bluesky.callbacks import CallbackBase
from dodal.log import LOGGER
from event_model.documents import Event, RunStart, RunStop
from redis import StrictRedis


class OmegaReading(TypedDict):
    value: float
    timestamp: float


def extrapolate_omega(
    latest_omega: OmegaReading, previous_omega: OmegaReading, image_timestamp: float
) -> float:
    omega_per_sec = (latest_omega["value"] - previous_omega["value"]) / (
        latest_omega["timestamp"] - previous_omega["timestamp"]
    )
    time_elapsed = image_timestamp - latest_omega["timestamp"]
    return latest_omega["value"] + time_elapsed * omega_per_sec


class MurkoCallback(CallbackBase):
    """A callback that triggers murko processing of images.

    It combines metadata readings from e.g the goniometer rotation with the uuid's given
    to us by an `OAVToRedisForwarder` (which describe the location of images in redis).
    And writes these as a package to redis. A separate service then forwards this to murko.

    The metadata and image data arrive independently, it is expected that the image data
    is arriving at a faster rate than gonio metadata and so the value of omega for when
    the image arrives is extrapolated based on previous omega readings.
    """

    DATA_EXPIRY_DAYS = 7

    def __init__(self, redis_host: str, redis_password: str, redis_db: int = 0):
        self.redis_client = StrictRedis(
            host=redis_host, password=redis_password, db=redis_db
        )
        self.last_uuid = None
        self.previous_omegas: list[OmegaReading] = []

    def start(self, doc: RunStart) -> RunStart | None:
        self.sample_id = doc.get("sample_id")
        self.murko_metadata = {
            "zoom_percentage": doc.get("zoom_percentage"),
            "microns_per_x_pixel": doc.get("microns_per_x_pixel"),
            "microns_per_y_pixel": doc.get("microns_per_y_pixel"),
            "beam_centre_i": doc.get("beam_centre_i"),
            "beam_centre_j": doc.get("beam_centre_j"),
            "sample_id": self.sample_id,
        }
        self.last_uuid = None
        self.previous_omegas = []
        LOGGER.info(f"Starting to stream metadata to murko under {self.sample_id}")
        return doc

    def event(self, doc: Event) -> Event:
        if latest_omega := doc["data"].get("smargon-omega"):
            if len(self.previous_omegas) <= 2 and self.last_uuid:
                # For the first few images there's not enough data to extrapolate so we
                # match them one to one
                self.call_murko(self.last_uuid, latest_omega)
            self.previous_omegas.append(
                OmegaReading(
                    value=latest_omega,
                    timestamp=doc["timestamps"]["smargon-omega"],
                )
            )
        elif (uuid := doc["data"].get("oav_to_redis_forwarder-uuid")) is not None:
            if len(self.previous_omegas) >= 2:
                omega = extrapolate_omega(
                    self.previous_omegas[-1],
                    self.previous_omegas[-2],
                    doc["timestamps"]["oav_to_redis_forwarder-uuid"],
                )
                LOGGER.info(f"Using extrapolated omega of {omega}")
                self.call_murko(uuid, omega)
            self.last_uuid = uuid
        return doc

    def call_murko(self, uuid: str, omega: float):
        metadata = copy.deepcopy(self.murko_metadata)
        metadata["omega_angle"] = omega
        metadata["uuid"] = uuid

        # Send metadata to REDIS and trigger murko
        redis_key = f"murko:{metadata['sample_id']}:metadata"
        self.redis_client.hset(redis_key, uuid, json.dumps(metadata))
        self.redis_client.expire(redis_key, timedelta(days=self.DATA_EXPIRY_DAYS))
        self.redis_client.publish("murko", json.dumps(metadata))

    def stop(self, doc: RunStop) -> RunStop | None:
        LOGGER.info(f"Finished streaming {self.sample_id} to murko")
        return doc
