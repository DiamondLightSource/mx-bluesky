import gzip
import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch

import bluesky.preprocessors as bpp
from bluesky.run_engine import RunEngine
from dodal.beamlines import i03
from dodal.devices.oav.oav_parameters import OAVConfig
from ophyd_async.testing import set_mock_value

from mx_bluesky.common.plans.read_hardware import (
    standard_read_hardware_during_collection,
)
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    RotationScanComposite,
)
from mx_bluesky.hyperion.external_interaction.callbacks.rotation.nexus_callback import (
    RotationNexusFileCallback,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.rotation import MultiRotationScan

DISPLAY_CONFIGURATION = "tests/test_data/test_display.configuration"
ZOOM_LEVELS_XML = "tests/test_data/test_jCameraManZoomLevels.xml"
TEST_DATA_DIRECTORY = Path("tests/test_data/nexus_files/rotation")
TEST_METAFILE = "ins_8_5_meta.h5.gz"
FAKE_DATAFILE = "../fake_data.h5"
FILENAME_STUB = "test_rotation_nexus"


def test_params(filename_stub, dir):
    def get_params(filename):
        with open(filename) as f:
            return json.loads(f.read())

    params = MultiRotationScan(
        **get_params(
            "tests/test_data/parameter_json_files/good_test_one_multi_rotation_scan_parameters.json"
        )
    )
    for scan_params in params.rotation_scans:
        scan_params.x_start_um = 0
        scan_params.y_start_um = 0
        scan_params.z_start_um = 0
        scan_params.scan_width_deg = 360
    params.file_name = filename_stub
    params.demand_energy_ev = 12700
    params.storage_directory = str(dir)
    params.exposure_time_s = 0.004
    return params


def fake_rotation_scan(
    parameters: MultiRotationScan,
    subscription: RotationNexusFileCallback,
    rotation_devices: RotationScanComposite,
):
    single_scan_parameters = next(parameters.single_rotation_scans)

    @bpp.subs_decorator(subscription)
    @bpp.set_run_key_decorator("rotation_scan_with_cleanup_and_subs")
    @bpp.run_decorator(  # attach experiment metadata to the start document
        md={
            "subplan_name": CONST.PLAN.ROTATION_OUTER,
            "mx_bluesky_parameters": single_scan_parameters.model_dump_json(),
            "activate_callbacks": "RotationNexusFileCallback",
        }
    )
    def plan():
        yield from standard_read_hardware_during_collection(
            rotation_devices.aperture_scatterguard,
            rotation_devices.attenuator,
            rotation_devices.flux,
            rotation_devices.dcm,
            rotation_devices.eiger,
        )

    return plan()


def fake_create_rotation_devices():
    beamstop = i03.beamstop(connect_immediately=True, mock=True)
    eiger = i03.eiger(connect_immediately=True, mock=True)
    smargon = i03.smargon(connect_immediately=True, mock=True)
    zebra = i03.zebra(connect_immediately=True, mock=True)
    detector_motion = i03.detector_motion(connect_immediately=True, mock=True)
    backlight = i03.backlight(mock=True)
    attenuator = i03.attenuator(connect_immediately=True, mock=True)
    flux = i03.flux(connect_immediately=True, mock=True)
    undulator = i03.undulator(connect_immediately=True, mock=True)
    aperture_scatterguard = i03.aperture_scatterguard(
        connect_immediately=True, mock=True
    )
    synchrotron = i03.synchrotron(connect_immediately=True, mock=True)
    s4_slit_gaps = i03.s4_slit_gaps(connect_immediately=True, mock=True)
    dcm = i03.dcm(connect_immediately=True, mock=True)
    robot = i03.robot(connect_immediately=True, mock=True)
    oav = i03.oav(
        connect_immediately=True,
        mock=True,
        params=OAVConfig(
            zoom_params_file=ZOOM_LEVELS_XML, display_config_file=DISPLAY_CONFIGURATION
        ),
    )
    xbpm_feedback = i03.xbpm_feedback(connect_immediately=True, mock=True)

    set_mock_value(smargon.omega.max_velocity, 131)
    set_mock_value(dcm.energy_in_kev.user_readback, 12700)

    return RotationScanComposite(
        attenuator=attenuator,
        backlight=backlight,
        beamstop=beamstop,
        dcm=dcm,
        detector_motion=detector_motion,
        eiger=eiger,
        flux=flux,
        smargon=smargon,
        undulator=undulator,
        aperture_scatterguard=aperture_scatterguard,
        synchrotron=synchrotron,
        s4_slit_gaps=s4_slit_gaps,
        zebra=zebra,
        robot=robot,
        oav=oav,
        sample_shutter=i03.sample_shutter(connect_immediately=True, mock=True),
        xbpm_feedback=xbpm_feedback,
    )


def sim_rotation_scan_to_create_nexus(
    test_params: MultiRotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    filename_stub,
    RE,
):
    run_number = test_params.detector_params.run_number
    nexus_filename = f"{filename_stub}_{run_number}.nxs"

    fake_create_rotation_devices.eiger.bit_depth.sim_put(32)  # type: ignore

    with patch(
        "mx_bluesky.common.external_interaction.nexus.write_nexus.get_start_and_predicted_end_time",
        return_value=("test_time", "test_time"),
    ):
        RE(
            fake_rotation_scan(
                test_params, RotationNexusFileCallback(), fake_create_rotation_devices
            )
        )

    nexus_path = Path(test_params.storage_directory) / nexus_filename
    assert os.path.isfile(nexus_path)
    return filename_stub, run_number


def extract_metafile(input_filename, output_filename):
    with gzip.open(input_filename) as metafile_fo:
        with open(output_filename, "wb") as output_fo:
            output_fo.write(metafile_fo.read())


def _generate_fake_nexus(filename, dir=os.getcwd()):
    RE = RunEngine({})
    params = test_params(filename, dir)
    run_number = params.detector_params.run_number
    filename_stub, run_number = sim_rotation_scan_to_create_nexus(
        params, fake_create_rotation_devices(), filename, RE
    )
    return filename_stub, run_number


def generate_test_nexus():
    filename_stub, run_number = _generate_fake_nexus(FILENAME_STUB)
    # ugly hack because we get double free error on exit
    with open("OUTPUT_FILENAME", "x") as f:
        f.write(f"{filename_stub}_{run_number}.nxs")

    extract_metafile(
        str(TEST_DATA_DIRECTORY / TEST_METAFILE),
        f"{FILENAME_STUB}_{run_number}_meta.h5",
    )

    new_hyp_data = [f"{FILENAME_STUB}_{run_number}_00000{n}.h5" for n in [1, 2, 3, 4]]
    [shutil.copy(TEST_DATA_DIRECTORY / FAKE_DATAFILE, d) for d in new_hyp_data]

    exit(0)


def copy_test_meta_data_files():
    extract_metafile(
        str(TEST_DATA_DIRECTORY / TEST_METAFILE),
        f"{TEST_DATA_DIRECTORY}/ins_8_5_meta.h5",
    )
    new_data = [f"{TEST_DATA_DIRECTORY}/ins_8_5_00000{n}.h5" for n in [1, 2, 3, 4]]
    [shutil.copy(TEST_DATA_DIRECTORY / FAKE_DATAFILE, d) for d in new_data]


if __name__ == "__main__":
    generate_test_nexus()
