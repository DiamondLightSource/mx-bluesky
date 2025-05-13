import io
import json
import pickle
from datetime import timedelta
from typing import TypedDict

import numpy as np
import zmq
from dodal.devices.i04.constants import RedisConstants
from numpy.typing import NDArray
from PIL import Image
from redis import StrictRedis

from mx_bluesky.common.utils.log import LOGGER

MURKO_ADDRESS = "tcp://i04-murko-prod.diamond.ac.uk:8008"

MurkoResult = dict
FullMurkoResults = dict[str, list[MurkoResult]]


class MurkoRequest(TypedDict):
    """See https://github.com/MartinSavko/murko#usage for more information."""

    to_predict: NDArray
    model_img_size: tuple[int, int]
    save: bool
    min_size: int
    description: list

    # The identifier for each image
    prefix: list[str]


def get_image_size(image: NDArray) -> tuple[int, int]:
    """Returns the width and height of a numpy image"""
    return image.shape[1], image.shape[0]


def send_to_murko_and_get_results(request: MurkoRequest) -> FullMurkoResults:
    LOGGER.info(f"Sending {request['prefix']} to murko")
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect(MURKO_ADDRESS)
    socket.send(pickle.dumps(request))
    raw_results = socket.recv()
    assert isinstance(raw_results, bytes)
    results = pickle.loads(raw_results)
    LOGGER.info(f"Got {len(results['descriptions'])} results")
    return results


def _correlate_results_to_uuids(
    request: MurkoRequest, murko_results: FullMurkoResults
) -> list[tuple[str, MurkoResult]]:
    """We send a batch of images to murko, with each having a 'prefix' of the uuid that
    we're using to keep track of the image. Murko sends back an ordered list of these,
    which we match to the supplied prefix here."""
    return list(zip(request["prefix"], murko_results["descriptions"], strict=False))


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
        results = send_to_murko_and_get_results(request_arguments)
        results_with_uuids = _correlate_results_to_uuids(request_arguments, results)
        self._send_murko_results_to_redis(sample_id, results_with_uuids)

    def _send_murko_results_to_redis(
        self, sample_id: str, results: list[tuple[str, MurkoResult]]
    ):
        """Stores the results into a redis hash (for longer term storage) and publishes
        them as well so that downstream clients can get notified."""
        for uuid, result in results:
            redis_key = f"murko:{sample_id}:results"
            self.redis_client.hset(redis_key, uuid, str(pickle.dumps(result)))
            self.redis_client.expire(redis_key, timedelta(days=7))
        self.redis_client.publish("murko-results", pickle.dumps(results))

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
        redis_host=RedisConstants.REDIS_HOST,
        redis_password=RedisConstants.REDIS_PASSWORD,
        db=RedisConstants.MURKO_REDIS_DB,
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
            image_key = f"murko:{sample_id}:raw"
            raw_image = self.redis_client.hget(image_key, uuid)

            if not isinstance(raw_image, bytes):
                LOGGER.warning(
                    f"Image at {image_key}:{uuid} is {raw_image}, expected bytes. Ignoring the data"
                )
                return

            image = Image.open(io.BytesIO(raw_image))
            image = np.asarray(image)

            self.forwarder.add(sample_id, uuid, image)

        elif not message:
            self.forwarder.flush()

    def listen_for_image_data_forever(self):
        self.pubsub.subscribe(self.channel)

        while True:
            self._get_and_handle_message()


def main():
    client = RedisListener()
    client.listen_for_image_data_forever()


if __name__ == "__main__":
    main()
