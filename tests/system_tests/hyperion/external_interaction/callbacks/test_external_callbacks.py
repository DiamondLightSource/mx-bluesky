from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
from collections.abc import Mapping
from genericpath import isfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from time import sleep
from typing import Any
from unittest.mock import MagicMock, patch

import bluesky.plan_stubs as bps
import pytest
import zmq
from blueapi.config import ApplicationConfig, ConfigLoader
from blueapi.core import BlueskyContext, DataEvent, EventPublisher
from bluesky.callbacks import CallbackBase
from bluesky.callbacks.zmq import Publisher
from bluesky.run_engine import RunEngine
from bluesky_stomp.messaging import MessageContext, StompClient
from bluesky_stomp.models import Broker, MessageTopic
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.smargon import Smargon
from zmq.utils.monitor import recv_monitor_message

from mx_bluesky.common.experiment_plans.common_flyscan_xray_centre_plan import (
    common_flyscan_xray_centre,
)
from mx_bluesky.common.external_interaction.callbacks.xray_centre.ispyb_callback import (
    ispyb_activation_decorator,
)
from mx_bluesky.common.parameters.rotation import (
    RotationScan,
)
from mx_bluesky.common.utils.log import LOGGER
from mx_bluesky.common.utils.utils import convert_angstrom_to_ev
from mx_bluesky.hyperion.experiment_plans.hyperion_flyscan_xray_centre_plan import (
    construct_hyperion_specific_features,
)
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    rotation_scan,
)
from mx_bluesky.hyperion.external_interaction.callbacks.stomp.dispatcher import (
    BLUEAPI_EVENT_TOPIC,
)
from mx_bluesky.hyperion.parameters.constants import CONST, HyperionConstants
from mx_bluesky.hyperion.parameters.device_composites import (
    HyperionFlyScanXRayCentreComposite,
)
from mx_bluesky.hyperion.parameters.gridscan import HyperionSpecifiedThreeDGridScan

from .....conftest import fake_read
from ..conftest import fetch_comment  # noqa  # type: ignore
from .stomp_callback_wrapper.__main__ import CALLBACK_TOPIC

"""
Note that because these tests use the external processes some of the errors coming from
them may not be very informative. You will want to check the log files produced in `tmp`
for better logs.
"""


TASK_ID = "TASK_ID"


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


def external_callbacks_with_args(*args):
    process_env = os.environ.copy()
    external_callbacks_process = subprocess.Popen(
        [sys.executable, *args], env=process_env
    )
    yield external_callbacks_process
    external_callbacks_process.send_signal(signal.SIGINT)
    sleep(0.01)
    external_callbacks_process.kill()
    external_callbacks_process.wait(10)


@pytest.fixture
def external_callbacks():
    yield from external_callbacks_with_args(
        "-m",
        "mx_bluesky.hyperion.external_interaction.callbacks",
        "--dev",
        "--watchdog-port",
        str(HyperionConstants.HYPERION_PORT),
    )


@pytest.fixture
def external_callbacks_with_stomp():
    yield from external_callbacks_with_args(
        "tests/system_tests/hyperion/external_interaction/callbacks/stomp_callback_wrapper/__main__.py",
        "--dev",
        "--watchdog-port",
        str(HyperionConstants.HYPERION_PORT),
        "--stomp-config",
        "tests/test_data/stomp_callback_test_config.yaml",
    )


@pytest.fixture
def bluesky_context_with_stomp(run_engine: RunEngine):
    loader = ConfigLoader(ApplicationConfig)
    loader.use_values_from_yaml(Path("tests/test_data/stomp_callback_test_config.yaml"))
    config = loader.load()
    context = BlueskyContext(configuration=config, run_engine=run_engine)
    stomp_client = StompClient.for_broker(
        broker=Broker(
            host=config.stomp.url.host,
            port=config.stomp.url.port,
            auth=config.stomp.auth,
        )
    )

    event_publisher = EventPublisher()

    def fire_event(name: str, doc: Mapping[str, Any]):
        event_publisher.publish(DataEvent(name=name, doc=doc, task_id=TASK_ID))

    re_sub_id = context.run_engine.subscribe(fire_event)
    stomp_client.connect()

    def send_message(event, correlation_id):
        stomp_client.send(MessageTopic(name=BLUEAPI_EVENT_TOPIC), event, correlation_id)

    publisher_sub_id = event_publisher.subscribe(send_message)

    try:
        yield context, stomp_client
    finally:
        event_publisher.unsubscribe(publisher_sub_id)
        stomp_client.disconnect()
        context.run_engine.unsubscribe(re_sub_id)


@pytest.fixture
def run_engine_with_external_callbacks(
    external_callbacks,
    zocalo_env,  # ZOCALO_CONFIG must be exported to external callback environment
    run_engine,
):
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

    sub_id = run_engine.subscribe(publisher)

    yield run_engine

    run_engine.unsubscribe(sub_id)
    publisher.close()

    t.join()


@pytest.mark.system_test
def test_run_engine_with_external_callbacks_starts_and_stops(
    run_engine_with_external_callbacks: RunEngine,
):
    run_engine = run_engine_with_external_callbacks

    def plan():
        yield from bps.sleep(1)

    run_engine(plan())


@pytest.mark.system_test
async def test_external_callbacks_handle_gridscan_ispyb_and_zocalo(
    oav_for_system_test: OAV,
    smargon: Smargon,
    run_engine_with_external_callbacks: RunEngine,
    dummy_params: HyperionSpecifiedThreeDGridScan,
    fgs_composite_for_fake_zocalo: HyperionFlyScanXRayCentreComposite,
    fetch_comment,  # noqa
    fetch_datacollection_ids_for_group_id,
    fake_grid_snapshot_plan,
):
    """
    This test requires fake zocalo, and a connection to the dev ISPyB database.
    """

    run_engine = run_engine_with_external_callbacks

    doc_catcher = DocumentCatcher()
    run_engine.subscribe(doc_catcher)

    # Run the xray centring plan
    beamline_specific = construct_hyperion_specific_features(
        fgs_composite_for_fake_zocalo, dummy_params
    )

    @ispyb_activation_decorator(dummy_params)
    def wrapped_xray_centre():
        yield from fake_grid_snapshot_plan(smargon, oav_for_system_test)
        yield from common_flyscan_xray_centre(
            fgs_composite_for_fake_zocalo, dummy_params, beamline_specific
        )

    run_engine(wrapped_xray_centre())

    # get dcids from zocalo device
    dcid_reading = await fgs_composite_for_fake_zocalo.zocalo.ispyb_dcid.read()
    dcgid_reading = await fgs_composite_for_fake_zocalo.zocalo.ispyb_dcgid.read()

    dcid = dcid_reading["zocalo-ispyb_dcid"]["value"]
    dcgid = dcgid_reading["zocalo-ispyb_dcgid"]["value"]

    assert dcid != 0
    assert dcgid != 0

    dcids = fetch_datacollection_ids_for_group_id(dcgid)

    assert dcid in dcids

    # check the data in dev ispyb corresponding to this "collection"
    ispyb_comment1 = fetch_comment(dcids[0])
    ispyb_comment2 = fetch_comment(dcids[1])
    assert ispyb_comment1 != "" and ispyb_comment2 != ""
    assert (
        "Zocalo processing took" in ispyb_comment1
        or "Zocalo processing took" in ispyb_comment2
    )


@pytest.mark.system_test
def test_remote_callbacks_write_to_dev_ispyb_for_rotation(
    run_engine_with_external_callbacks: RunEngine,
    params_for_rotation_scan: RotationScan,
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
    params_for_rotation_scan.demand_energy_ev = convert_angstrom_to_ev(test_wl)

    with patch("bluesky.preprocessors.__read_and_stash_a_motor", fake_read):
        run_engine_with_external_callbacks(
            rotation_scan(
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


@pytest.mark.system_test
def test_external_callbacks_ping(external_callbacks):
    ping_received = threading.Event()

    class PingHTTPRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            assert self.path == "/callbackPing"
            ping_received.set()

    httpd = HTTPServer(("localhost", CONST.HYPERION_PORT), PingHTTPRequestHandler)
    server_thread = threading.Thread(
        group=None, target=httpd.serve_forever, daemon=True
    )
    try:
        server_thread.start()
        ping_received.wait(5)
    finally:
        httpd.shutdown()
        server_thread.join()


@pytest.mark.system_test
def test_external_callbacks_with_stomp(
    external_callbacks_with_stomp, bluesky_context_with_stomp
):
    bluesky_context, stomp_client = bluesky_context_with_stomp

    def read_the_baton():
        yield from bps.open_run(md={"run_name": "READ BATON PLAN"})
        baton = bluesky_context.find_device("baton")
        yield from bps.abs_set(baton.requested_user, "TEST_USER")
        yield from bps.create(name="BATON_READ_EVENT")
        yield from bps.read(baton)
        yield from bps.save()
        yield from bps.close_run()

    msgs = []

    started = threading.Event()
    stopped = threading.Event()

    def on_msg_from_callback(msg: str, context: MessageContext):
        msgs.append(msg)
        if msg == "stop":
            stopped.set()

    sub_id = stomp_client.subscribe(
        MessageTopic(name=CALLBACK_TOPIC), on_msg_from_callback
    )

    try:
        started.wait(10)
        bluesky_context.run_engine(read_the_baton())
        stopped.wait(10)
    finally:
        stomp_client.unsubscribe(sub_id)

    assert msgs == ["init", "start: READ BATON PLAN", "event: TEST_USER", "stop"]
