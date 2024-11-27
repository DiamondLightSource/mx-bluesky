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
from dodal.devices.zocalo.zocalo_results import (
    ZocaloResults,
    get_processing_results_from_event,
)
from zmq.utils.monitor import recv_monitor_message

from mx_bluesky.hyperion.experiment_plans.flyscan_xray_centre_plan import (
    FlyScanXRayCentreComposite,
    flyscan_xray_centre,
)
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    RotationScanComposite,
    rotation_scan,
)
from mx_bluesky.hyperion.log import LOGGER
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.gridscan import HyperionThreeDGridScan
from mx_bluesky.hyperion.parameters.rotation import RotationScan
from mx_bluesky.hyperion.utils.utils import convert_angstrom_to_eV

from .....conftest import fake_read
from ..conftest import (  # noqa
    TEST_RESULT_LARGE,
    TEST_RESULT_MEDIUM,
    fetch_comment,
    zocalo_env,
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
def RE_with_external_callbacks():
    RE = RunEngine()
    old_ispyb_config = os.environ.get("ISPYB_CONFIG_PATH")

    process_env = os.environ.copy()
    process_env["ISPYB_CONFIG_PATH"] = CONST.SIM.DEV_ISPYB_DATABASE_CFG

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
    if old_ispyb_config:
        os.environ["ISPYB_CONFIG_PATH"] = old_ispyb_config


@pytest.mark.s03
def test_RE_with_external_callbacks_starts_and_stops(
    RE_with_external_callbacks: RunEngine,
):
    RE = RE_with_external_callbacks

    def plan():
        yield from bps.sleep(1)

    RE(plan())


@pytest.mark.s03
async def test_external_callbacks_handle_gridscan_ispyb_and_zocalo(
    RE_with_external_callbacks: RunEngine,
    zocalo_env,  # noqa
    test_fgs_params: HyperionThreeDGridScan,
    fgs_composite_for_fake_zocalo: FlyScanXRayCentreComposite,
    done_status,
    zocalo_device: ZocaloResults,
    fetch_comment,  # noqa
):
    """This test doesn't actually require S03 to be running, but it does require fake
    zocalo, and a connection to the dev ISPyB database; like S03 tests, it can only run
    locally at DLS."""

    RE = RE_with_external_callbacks

    doc_catcher = DocumentCatcher()
    RE.subscribe(doc_catcher)

    # Run the xray centring plan
    RE(flyscan_xray_centre(fgs_composite_for_fake_zocalo, test_fgs_params))

    # Check that we we emitted a valid reading from the zocalo device
    zocalo_event = doc_catcher.event.call_args.args[0]  # type: ignore
    # TEST_RESULT_LARGE is what fake_zocalo sends by default
    assert (
        get_processing_results_from_event("zocalo", zocalo_event) == TEST_RESULT_LARGE
    )

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
    assert "Position (grid boxes) ['1', '2', '3']" in ispyb_comment
    assert "Size (grid boxes) [6 6 5];" in ispyb_comment


@pytest.mark.s03()
def test_remote_callbacks_write_to_dev_ispyb_for_rotation(
    RE_with_external_callbacks: RunEngine,
    test_rotation_params: RotationScan,
    fetch_comment,  # noqa
    fetch_datacollection_attribute,
    undulator,
    attenuator,
    synchrotron,
    s4_slit_gaps,
    flux,
    robot,
    aperture_scatterguard,
    fake_create_devices,
    sample_shutter,
    xbpm_feedback,
):
    test_wl = 0.71
    test_bs_x = 0.023
    test_bs_y = 0.047
    test_exp_time = 0.023
    test_img_wid = 0.27

    test_rotation_params.rotation_increment_deg = test_img_wid
    test_rotation_params.exposure_time_s = test_exp_time
    test_rotation_params.demand_energy_ev = convert_angstrom_to_eV(test_wl)

    composite = RotationScanComposite(
        aperture_scatterguard=aperture_scatterguard,
        attenuator=attenuator,
        backlight=fake_create_devices["backlight"],
        dcm=fake_create_devices["dcm"],
        detector_motion=fake_create_devices["detector_motion"],
        eiger=fake_create_devices["eiger"],
        flux=flux,
        smargon=fake_create_devices["smargon"],
        undulator=undulator,
        synchrotron=synchrotron,
        s4_slit_gaps=s4_slit_gaps,
        zebra=fake_create_devices["zebra"],
        robot=robot,
        oav=fake_create_devices["oav"],
        sample_shutter=sample_shutter,
        xbpm_feedback=xbpm_feedback,
    )

    with patch("bluesky.preprocessors.__read_and_stash_a_motor", fake_read):
        RE_with_external_callbacks(
            rotation_scan(
                composite,
                test_rotation_params,
            )
        )

    sleep(1)
    assert isfile("tmp/dev/hyperion_ispyb_callback.log")
    ispyb_log_tail = subprocess.run(
        ["tail", "tmp/dev/hyperion_ispyb_callback.log"],
        timeout=1,
        stdout=subprocess.PIPE,
    ).stdout.decode("utf-8")

    ids_re = re.compile(r"data_collection_ids=(\d+) data_collection_group_id=(\d+) ")
    matches = ids_re.findall(ispyb_log_tail)

    dcid = matches[0][0]

    comment = fetch_comment(dcid)
    assert comment == "Hyperion rotation scan"
    wavelength = fetch_datacollection_attribute(dcid, "wavelength")
    beamsize_x = fetch_datacollection_attribute(dcid, "beamSizeAtSampleX")
    beamsize_y = fetch_datacollection_attribute(dcid, "beamSizeAtSampleY")
    exposure = fetch_datacollection_attribute(dcid, "exposureTime")

    assert wavelength == test_wl
    assert beamsize_x == test_bs_x
    assert beamsize_y == test_bs_y
    assert exposure == test_exp_time
