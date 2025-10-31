import datetime
import os


def get_ispyb_config() -> str:
    ispyb_config = os.environ.get("ISPYB_CONFIG_PATH")
    assert ispyb_config, "ISPYB_CONFIG_PATH must be set"
    return ispyb_config


def get_current_time_string():
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")
