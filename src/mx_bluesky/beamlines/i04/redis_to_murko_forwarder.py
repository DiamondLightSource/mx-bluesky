import io
import json
import pickle
from typing import TypedDict

import numpy as np
import zmq
from dodal.beamlines.i04 import MURKO_REDIS_DB, REDIS_HOST, REDIS_PASSWORD
from numpy.typing import NDArray
from PIL import Image
from redis import StrictRedis

from mx_bluesky.common.utils.log import LOGGER

MURKO_ADDRESS = "tcp://i04-murko-prod.diamond.ac.uk:8008"


class MurkoRequest(TypedDict):
    to_predict: NDArray
    model_img_size: tuple[int, int]
    save: bool
    min_size: int
    description: list
    prefix: list[str]


def get_image_size(image: NDArray) -> tuple[int, int]:
    """Returns the width and height of a numpy image"""
    return image.shape[1], image.shape[0]


def send_to_murko_and_get_results(request: MurkoRequest) -> dict:
    LOGGER.info(f"Sending {request['prefix']} to murko")
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect(MURKO_ADDRESS)
    socket.send(pickle.dumps(request))
    raw_results = socket.recv()
    results = pickle.loads(raw_results)
    LOGGER.info(f"Got {len(results['descriptions'])} results")
    return results


def correlate_results_to_uuids(request: MurkoRequest, murko_results: dict) -> list:
    results = []
    uuids = request["prefix"]

    width, height = get_image_size(request["to_predict"][0])

    for uuid, prediction in zip(uuids, murko_results["descriptions"], strict=False):
        coords = prediction["most_likely_click"]
        y_coord = coords[0] * height
        x_coord = coords[1] * width
        results.append(
            {"uuid": uuid, "x_pixel_coord": x_coord, "y_pixel_coord": y_coord}
        )
    return results


class BatchMurkoForwarder:
    def __init__(self, redis_client: StrictRedis, batch_size: int):
        """
        Holds image data streamed from redis and forwards it to murko when:
            * A set number have been received
            * The shape of the images changes
            * When `flush` is called

        Once data has been forwarded this will then wait on the results and put them
        back in redis.

        Args:
            redis_client: The client to send murko results back to redis.
            batch_size: How many results to accumulate until they are flushed to redis.
        """
        self.redis_client = redis_client
        self.batch_size = batch_size
        self._uuids_and_images: dict[str, NDArray] = {}
        self._last_image_size: tuple[int, int] | None = None
        self._last_sample_id = ""

    def _handle_batch_of_images(self, sample_id, images, uuids):
        request_arguments: MurkoRequest = {
            "model_img_size": (256, 320),
            "to_predict": np.array(images),
            "save": False,
            "min_size": 64,
            "description": [
                "foreground",
                "crystal",
                "loop_inside",
                "loop",
                ["crystal", "loop"],
                ["crystal", "loop", "stem"],
            ],
            "prefix": uuids,
        }
        predictions = send_to_murko_and_get_results(request_arguments)
        results = correlate_results_to_uuids(request_arguments, predictions)
        self._send_murko_results_to_redis(sample_id, results)

    def _send_murko_results_to_redis(self, sample_id: str, results: list):
        for result in results:
            self.redis_client.hset(
                f"murko:{sample_id}:results", result["uuid"], json.dumps(result)
            )
        self.redis_client.publish("murko-results", json.dumps(results))

    def add(self, sample_id: str, uuid: str, image: NDArray):
        """Add an image to the batch to send to murko."""
        image_size = get_image_size(image)
        self._last_sample_id = sample_id
        if self._last_image_size and self._last_image_size != image_size:
            self.flush()
        self._uuids_and_images[uuid] = image
        self._last_image_size = image_size
        if len(self._uuids_and_images.keys()) >= self.batch_size:
            self.flush()

    def flush(self):
        """Flush the batch to murko."""
        if self._uuids_and_images:
            self._handle_batch_of_images(
                self._last_sample_id,
                list(self._uuids_and_images.values()),
                list(self._uuids_and_images.keys()),
            )
        self._uuids_and_images = {}
        self._last_image_size = None


class RedisListener:
    TIMEOUT_S = 2

    def __init__(
        self,
        redis_host=REDIS_HOST,
        redis_password=REDIS_PASSWORD,
        db=MURKO_REDIS_DB,
        redis_channel="murko",
    ):
        self.redis_client = StrictRedis(
            host=redis_host,
            password=redis_password,
            db=db,
        )
        self.pubsub = self.redis_client.pubsub()
        self.channel = redis_channel
        self.forwarder = BatchMurkoForwarder(self.redis_client, 10)

    def _get_and_handle_message(self):
        message = self.pubsub.get_message(timeout=self.TIMEOUT_S)
        if message and message["type"] == "message":
            data = json.loads(message["data"])
            LOGGER.info(f"Received from redis: {data}")
            uuid = data["uuid"]
            sample_id = data["sample_id"]

            # Images are put in redis as raw jpeg bytes, murko needs numpy arrays
            raw_image = self.redis_client.hget(f"murko:{sample_id}:raw", uuid)
            assert isinstance(raw_image, bytes)
            image = Image.open(io.BytesIO(raw_image))
            image = np.asarray(image)

            self.forwarder.add(sample_id, uuid, image)

        elif not message:
            self.forwarder.flush()

    def listen_for_image_data_forever(self):
        self.pubsub.subscribe(self.channel)

        while True:
            self._get_and_handle_message()


if __name__ == "__main__":
    client = RedisListener()
    client.listen_for_image_data_forever()
