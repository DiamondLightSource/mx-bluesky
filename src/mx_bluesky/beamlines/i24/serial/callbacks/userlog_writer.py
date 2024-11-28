import json

from bluesky.callbacks import CallbackBase

from mx_bluesky.beamlines.i24.serial.log import SSX_LOGGER
from mx_bluesky.beamlines.i24.serial.parameters import FixedTargetParameters


# NOTE On second thought, this should be used for the user log at the end instead
# of the parameter files written/copied/moved etc at the beginning.
# I suspect the users will expect an user log, but not the rest of it.
class UserLogWriter(CallbackBase):
    parameters: FixedTargetParameters
    # beam_settings: # Need beam settings here for wavelength

    def stop(self, doc: dict):  # type: ignore
        userlog_path = self.parameters.visit / f"processing/{self.parameters.directory}"
        userlog_fid = f"{self.parameters.filename}"
        SSX_LOGGER.debug(f"Write a user log in {userlog_path}")

        userlog_path.mkdir(parents=True, exist_ok=True)

        json_params = self.parameters.model_dump_json()
        with open(userlog_path / userlog_fid, "w") as f:
            json.dump(json_params, f, indent=4)


# NOTE To finish this #575 needs to be merged
