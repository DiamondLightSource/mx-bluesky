import json

from bluesky.callbacks import CallbackBase

from mx_bluesky.beamlines.i24.serial.parameters import (
    ExtruderParameters,
    FixedTargetParameters,
)
from mx_bluesky.beamlines.i24.serial.parameters.constants import (
    PARAM_FILE_NAME,
    PARAM_FILE_PATH,
    PARAM_FILE_PATH_FT,
)


class ParameterFileWriter(CallbackBase):
    parameters: ExtruderParameters | FixedTargetParameters

    def start(self, doc: dict):  # type: ignore
        if doc.get("subplan_name") == "main_fixed_target_plan":
            param_path = PARAM_FILE_PATH_FT
        elif doc.get("subplan_name") == "main_extruder_plan":
            param_path = PARAM_FILE_PATH

        json_params = self.parameters.model_dump_json()
        with open(param_path / PARAM_FILE_NAME, "w") as f:
            json.dump(json_params, f, indent=4)
