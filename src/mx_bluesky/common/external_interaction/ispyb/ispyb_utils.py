from __future__ import annotations

import datetime
import os

from ispyb import NoResult
from ispyb.connector.mysqlsp.main import ISPyBMySQLSPConnector as Connector
from ispyb.sp.core import Core


def get_ispyb_config() -> str:
    ispyb_config = os.environ.get("ISPYB_CONFIG_PATH")
    assert ispyb_config, "ISPYB_CONFIG_PATH must be set"
    return ispyb_config


def get_session_id_from_visit(conn: Connector, visit: str):
    try:
        core: Core = conn.core
        return core.retrieve_visit_id(visit)
    except NoResult as e:
        raise NoResult(f"No session ID found in ispyb for visit {visit}") from e


def get_current_time_string():
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")
