import pickle
from collections import OrderedDict

import numpy as np
import zmq
from numpy.typing import NDArray


def create_murko_request(images: OrderedDict[str, NDArray]):
    return {
        "to_predict": np.asarray(list(images.values())),
        "model_img_size": (256, 320),
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
        "prefix": list(images.keys()),
    }


def convert_result_to_pixels(coord: tuple[float, float], image_shape: tuple):
    """Murko gives results as percentage along image, this needs to be converted to
    pixels using the image resolution."""
    return (coord[0] * image_shape[0], coord[1] * image_shape[1])


class RedisMurkoForwarder:
    def __init__(self, murko_address: str):
        self.murko_address = murko_address

    def _send_request_to_murko_and_return_results(self, request):
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect(self.murko_address)

        socket.send(pickle.dumps(request))
        return pickle.loads(socket.recv())

    def _send_results_to_redis(
        self, results: OrderedDict, uuids: list[str], image_shape: tuple
    ):
        for uuid, result in zip(uuids, results["descriptions"], strict=True):
            coords = result.pop("most_likely_click")
            result["most_likely_click_pixels"] = convert_result_to_pixels(
                coords, image_shape
            )
            result["uuid"] = uuid
