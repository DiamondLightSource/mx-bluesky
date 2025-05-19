from __future__ import annotations

import os
import re
import signal
import subprocess
import threading
from genericpath import isfile
from time import sleep
from unittest.mock import MagicMock, patch

import bluesky.plan_stubs as bps
import pytest
import zmq
from bluesky.callbacks import CallbackBase
from bluesky.callbacks.zmq import Publisher
from bluesky.run_engine import RunEngine
from zmq.utils.monitor import recv_monitor_message

from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    ispyb_activation_decorator,
)
from mx_bluesky.common.plans.common_flyscan_xray_centre_plan import (
    common_flyscan_xray_centre,
)
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.utils.utils import convert_angstrom_to_eV
from mx_bluesky.hyperion.experiment_plans.hyperion_flyscan_xray_centre_plan import (
    construct_hyperion_specific_features,
)
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    multi_rotation_scan,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.device_composites import (
    HyperionFlyScanXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import HyperionSpecifiedThreeDGridScan
from mx_bluesky.hyperion.parameters.rotation import MultiRotationScan

from .....conftest import fake_read
from ..conftest import (  # noqa
    fetch_comment,
)

"""
Note that because these tests use the external processes some of the errors coming from
them may not be very informative. You will want to check the log files produced in `tmp`
for better logs.
"""


class DocumentCatcher(CallbackBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start = MagicMock()
        self.descriptor = MagicMock()
        self.event = MagicMock()
        self.stop = MagicMock()


def event_monitor(monitor: zmq.Socket, connection_active_lock: threading.Lock) -> None:
    try:
        while monitor.poll():
            monitor_event = recv_monitor_message(monitor)
            LOGGER.info(f"Event: {monitor_event}")
            if monitor_event["event"] == zmq.EVENT_CONNECTED:
                LOGGER.info("CONNECTED - acquiring connection_active_lock")
                connection_active_lock.acquire()
            if monitor_event["event"] == zmq.EVENT_MONITOR_STOPPED:
                break
    except zmq.ZMQError:
        pass
    finally:
        connection_active_lock.release()
        monitor.close()
        LOGGER.info("event monitor thread done!")


@pytest.fixture
def RE_with_external_callbacks(
    zocalo_env,  # ZOCALO_CONFIG must be exported to external callback environment
):
    RE = RunEngine()

    process_env = os.environ.copy()

    external_callbacks_process = subprocess.Popen(
        [
            "python",
            "src/mx_bluesky/hyperion/external_interaction/callbacks/__main__.py",
            "--dev",
        ],
        env=process_env,
    )
    publisher = Publisher(f"localhost:{CONST.CALLBACK_0MQ_PROXY_PORTS[0]}")
    monitor = publisher._socket.get_monitor_socket()

    connection_active_lock = threading.Lock()
    t = threading.Thread(
        target=event_monitor,
        args=(monitor, connection_active_lock),
        name="event_monitor",
    )
    t.start()

    while not connection_active_lock.locked():
        sleep(0.1)  # wait for connection to happen before continuing

    sub_id = RE.subscribe(publisher)

    yield RE

    RE.unsubscribe(sub_id)
    publisher.close()

    external_callbacks_process.send_signal(signal.SIGINT)
    sleep(0.01)
    external_callbacks_process.kill()
    external_callbacks_process.wait(10)
    t.join()


@pytest.mark.system_test
def test_RE_with_external_callbacks_starts_and_stops(
    RE_with_external_callbacks: RunEngine,
):
    RE = RE_with_external_callbacks

    def plan():
        yield from bps.sleep(1)

    RE(plan())


@pytest.mark.system_test
async def test_external_callbacks_handle_gridscan_ispyb_and_zocalo(
    RE_with_external_callbacks: RunEngine,
    dummy_params: HyperionSpecifiedThreeDGridScan,
    fgs_composite_for_fake_zocalo: HyperionFlyScanXRayCentreComposite,
    done_status,
    fetch_comment,  # noqa
):
    """
    This test requires fake zocalo, and a connection to the dev ISPyB database.
    """

    RE = RE_with_external_callbacks

    doc_catcher = DocumentCatcher()
    RE.subscribe(doc_catcher)

    # Run the xray centring plan
    beamline_specific = construct_hyperion_specific_features(
        fgs_composite_for_fake_zocalo, dummy_params
    )

    @ispyb_activation_decorator(dummy_params)
    def wrapped_xray_centre():
        yield from common_flyscan_xray_centre(
            fgs_composite_for_fake_zocalo, dummy_params, beamline_specific
        )

    RE(wrapped_xray_centre())

    # get dcids from zocalo device
    dcid_reading = await fgs_composite_for_fake_zocalo.zocalo.ispyb_dcid.read()
    dcgid_reading = await fgs_composite_for_fake_zocalo.zocalo.ispyb_dcgid.read()

    dcid = dcid_reading["zocalo-ispyb_dcid"]["value"]
    dcgid = dcgid_reading["zocalo-ispyb_dcgid"]["value"]

    assert dcid != 0
    assert dcgid != 0

    # check the data in dev ispyb corresponding to this "collection"
    ispyb_comment = fetch_comment(dcid)
    assert ispyb_comment != ""
    assert "Zocalo processing took" in ispyb_comment


@pytest.mark.system_test
def test_remote_callbacks_write_to_dev_ispyb_for_rotation(
    RE_with_external_callbacks: RunEngine,
    params_for_rotation_scan: MultiRotationScan,
    fetch_comment,  # noqa
    fetch_datacollection_attribute,
    composite_for_rotation_scan,
    oav_parameters_for_rotation,
):
    test_wl = 0.71
    test_bs_x = 0.020
    test_bs_y = 0.020
    test_exp_time = 0.023
    test_img_wid = 0.27

    params_for_rotation_scan.rotation_increment_deg = test_img_wid
    params_for_rotation_scan.exposure_time_s = test_exp_time
    params_for_rotation_scan.demand_energy_ev = convert_angstrom_to_eV(test_wl)

    with patch("bluesky.preprocessors.__read_and_stash_a_motor", fake_read):
        RE_with_external_callbacks(
            multi_rotation_scan(
                composite_for_rotation_scan,
                params_for_rotation_scan,
                oav_parameters_for_rotation,
            )
        )

    sleep(1)
    assert isfile("/tmp/logs/bluesky/hyperion_ispyb_callback.log")
    ispyb_log_tail = subprocess.run(
        ["tail", "/tmp/logs/bluesky/hyperion_ispyb_callback.log"],
        timeout=1,
        stdout=subprocess.PIPE,
    ).stdout.decode("utf-8")

    ids_re = re.compile(
        r"data_collection_ids=\((\d+),\) data_collection_group_id=(\d+) "
    )
    matches = ids_re.findall(ispyb_log_tail)

    dcid = matches[0][0]

    comment = fetch_comment(dcid)
    assert comment == "test Sample position (µm): (1, 2, 3) Aperture: Small. "
    wavelength = fetch_datacollection_attribute(dcid, "wavelength")
    beamsize_x = fetch_datacollection_attribute(dcid, "beamSizeAtSampleX")
    beamsize_y = fetch_datacollection_attribute(dcid, "beamSizeAtSampleY")
    exposure = fetch_datacollection_attribute(dcid, "exposureTime")

    assert wavelength == test_wl
    assert beamsize_x == test_bs_x
    assert beamsize_y == test_bs_y
    assert exposure == test_exp_time
