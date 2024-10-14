import copy
import json

from bluesky.callbacks import CallbackBase
from dodal.log import LOGGER
from event_model.documents import Event, RunStart
from redis import StrictRedis


class MurkoCallback(CallbackBase):
    def __init__(self, redis_host: str, redis_password: str, redis_db: int = 0):
        self.redis_client = StrictRedis(
            host=redis_host, password=redis_password, db=redis_db
        )
        self.last_uuid = None

    def start(self, doc: RunStart) -> RunStart | None:
        self.murko_metadata = {
            "zoom_percentage": doc.get("zoom_percentage"),
            "microns_per_x_pixel": doc.get("microns_per_x_pixel"),
            "microns_per_y_pixel": doc.get("microns_per_y_pixel"),
            "beam_centre_i": doc.get("beam_centre_i"),
            "beam_centre_j": doc.get("beam_centre_j"),
            "sample_id": doc.get("sample_id"),
        }
        self.last_uuid = None
        return doc

    def event(self, doc: Event) -> Event:
        if latest_omega := doc["data"].get("smargon-omega"):
            if self.last_uuid is not None:
                self.call_murko(self.last_uuid, latest_omega)
        elif (uuid := doc["data"].get("oav_to_redis_forwarder-uuid")) is not None:
            self.last_uuid = uuid
        return doc

    def call_murko(self, uuid: str, omega: float):
        metadata = copy.deepcopy(self.murko_metadata)
        metadata["omega_angle"] = omega
        metadata["uuid"] = uuid

        # Send metadata to REDIS and trigger murko
        self.redis_client.hset("test-metadata", uuid, json.dumps(metadata))
        self.redis_client.publish("murko", json.dumps(metadata))
        LOGGER.info("Metadata sent to redis")
