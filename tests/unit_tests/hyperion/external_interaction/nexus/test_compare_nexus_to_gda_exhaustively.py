import json
import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import h5py
import pytest
from bluesky import RunEngine
from bluesky import preprocessors as bpp
from h5py import Dataset, Datatype, File, Group
from numpy import dtype

from mx_bluesky.common.experiment_plans.read_hardware import (
    standard_read_hardware_during_collection,
)
from mx_bluesky.hyperion.experiment_plans.rotation_scan_plan import (
    RotationScanComposite,
)
from mx_bluesky.hyperion.external_interaction.callbacks.rotation.nexus_callback import (
    RotationNexusFileCallback,
)
from mx_bluesky.hyperion.parameters.constants import CONST
from mx_bluesky.hyperion.parameters.rotation import RotationScan

from .....conftest import extract_metafile, raw_params_from_file

TEST_DATA_DIRECTORY = Path("tests/test_data/nexus_files/rotation")
TEST_EXAMPLE_NEXUS_FILE = Path("ins_8_5.nxs")
TEST_NEXUS_FILENAME = "rotation_scan_test_nexus"
TEST_METAFILE = "ins_8_5_meta.h5.gz"
FAKE_DATAFILE = "../fake_data.h5"

h5item = Group | Dataset | File | Datatype


def get_groups(dataset: h5py.File) -> set:
    e = set()

    def add_layer(s: set, d: h5item):
        if isinstance(d, h5py.Group):
            for k in d:
                s.add(d.name)
                add_layer(s, d[k])

    add_layer(e, dataset)
    return e


def has_equiv_in(item: str, groups: set, exception_table: dict[str, set[str]]):
    if item not in exception_table.keys():
        return False
    # one of the items in exception_table[item] must be in the tested groups
    return exception_table[item] & groups != set()


def test_has_equiv_in():
    test_table = {"a": {"b", "c"}}
    assert not has_equiv_in("a", {"x", "y", "z"}, test_table)
    assert has_equiv_in("a", {"x", "y", "c"}, test_table)


FilesAndgroups = tuple[h5py.File, set[str], h5py.File, set[str]]


@pytest.fixture
def files_and_groups(tmp_path, RE: RunEngine, fake_create_rotation_devices):
    tmpdir = tmp_path
    filename, run_number = _generate_fake_nexus(
        TEST_NEXUS_FILENAME, RE, fake_create_rotation_devices, tmp_path
    )
    extract_metafile(
        str(TEST_DATA_DIRECTORY / TEST_METAFILE),
        f"{tmpdir}/{filename}_{run_number}_meta.h5",
    )
    extract_metafile(
        str(TEST_DATA_DIRECTORY / TEST_METAFILE),
        f"{tmpdir}/ins_8_5_meta.h5",
    )
    new_hyperion_master = tmpdir / f"{filename}_{run_number}.nxs"
    new_gda_master = tmpdir / TEST_EXAMPLE_NEXUS_FILE
    new_gda_data = [tmpdir / f"ins_8_5_00000{n}.h5" for n in [1, 2, 3, 4]]
    new_hyp_data = [
        tmpdir / f"{filename}_{run_number}_00000{n}.h5" for n in [1, 2, 3, 4]
    ]
    shutil.copy(TEST_DATA_DIRECTORY / TEST_EXAMPLE_NEXUS_FILE, new_gda_master)
    [shutil.copy(TEST_DATA_DIRECTORY / FAKE_DATAFILE, d) for d in new_gda_data]
    [shutil.copy(TEST_DATA_DIRECTORY / FAKE_DATAFILE, d) for d in new_hyp_data]

    with (
        h5py.File(new_gda_master, "r") as example_nexus,
        h5py.File(new_hyperion_master, "r") as hyperion_nexus,
    ):
        yield (
            example_nexus,
            get_groups(example_nexus),
            hyperion_nexus,
            get_groups(hyperion_nexus),
        )


GROUPS_EQUIVALENTS_TABLE = {
    "/entry/instrument/source": {"/entry/source"},
    "/entry/instrument/detector_z": {"/entry/instrument/detector/detector_z"},
    "/entry/instrument/transformations": {"/entry/instrument/detector/transformations"},
}
GROUPS_EXCEPTIONS = {"/entry/instrument/attenuator"}


def test_hyperion_rotation_nexus_groups_against_gda(
    files_and_groups: FilesAndgroups,
):
    _, gda_groups, _, hyperion_groups = files_and_groups
    for item in gda_groups:
        assert (
            item in hyperion_groups
            or has_equiv_in(item, hyperion_groups, GROUPS_EQUIVALENTS_TABLE)
            or item in GROUPS_EXCEPTIONS
        )


DATATYPE_EXCEPTION_TABLE = {
    "/entry/instrument/detector/bit_depth_image": (
        dtype("int64"),
        "gda item bit_depth_image not present",
    ),
    "/entry/instrument/detector/depends_on": (dtype("S48"), dtype("S1024")),
    "/entry/instrument/detector/description": (dtype("S9"), dtype("S1024")),
    "/entry/instrument/detector/detector_readout_time": (
        dtype("int64"),
        "gda item detector_readout_time not present",
    ),
    "/entry/instrument/detector/distance": (
        dtype("<f8"),
        "gda item distance not present",
    ),
    "/entry/instrument/detector/photon_energy": (
        dtype("<f8"),
        "gda item photon_energy not present",
    ),
    "/entry/instrument/detector/sensor_material": (dtype("S2"), dtype("S1024")),
    "/entry/instrument/detector/threshold_energy": (
        dtype("<f8"),
        "gda item threshold_energy not present",
    ),
    "/entry/instrument/detector/type": (dtype("S5"), dtype("S1024")),
    "/entry/instrument/detector/underload_value": (
        dtype("int64"),
        "gda item underload_value not present",
    ),
    "/entry/sample/depends_on": (dtype("S33"), dtype("S1024")),
    "/entry/sample/sample_omega/omega_end": (
        dtype("<f8"),
        "gda item omega_end not present",
    ),
    "/entry/sample/sample_omega/omega_increment_set": (
        dtype("<f8"),
        "gda item omega_increment_set not present",
    ),
    "/entry/instrument/name": (dtype("S20"), dtype("S1024")),
    "/entry/end_time_estimated": (
        dtype("S20"),
        "gda item end_time_estimated not present",
    ),
    "/entry/start_time": (dtype("S10"), dtype("S20")),
    "/entry/data/data": (dtype("uint32"), dtype("int32")),
    "/entry/instrument/detector/detectorSpecific/nimages": (
        dtype("int64"),
        dtype("int32"),
    ),
    "/entry/instrument/detector/detectorSpecific/ntrigger": (
        dtype("int64"),
        "gda item ntrigger not present",
    ),
    "/entry/instrument/detector/detectorSpecific/software_version": (
        dtype("S100"),
        "gda item software_version not present",
    ),
    "/entry/instrument/detector/detectorSpecific/x_pixels": (
        dtype("uint32"),
        "gda item x_pixels not present",
    ),
    "/entry/instrument/detector/detectorSpecific/x_pixels_in_detector": (
        dtype("uint32"),
        dtype("int32"),
    ),
    "/entry/instrument/detector/detectorSpecific/y_pixels": (
        dtype("uint32"),
        "gda item y_pixels not present",
    ),
    "/entry/instrument/detector/detectorSpecific/y_pixels_in_detector": (
        dtype("uint32"),
        dtype("int32"),
    ),
    "/entry/instrument/detector/module/data_origin": (dtype("uint32"), dtype("int32")),
    "/entry/instrument/detector/module/data_size": (dtype("uint32"), dtype("int32")),
    "/entry/instrument/detector/module/data_stride": (dtype("uint32"), dtype("int32")),
}


def mockitem(name, item):
    m = MagicMock()
    m.dtype = f"{name} item {item} not present"
    return m


@pytest.mark.timeout(2)
def test_determine_datatype_differences(
    files_and_groups: FilesAndgroups,
):
    gda_nexus, gda_groups, hyperion_nexus, hyperion_groups = files_and_groups
    diffs = {}
    for item in gda_groups:
        # we checked separately if all expected items should be there
        # but we should probably still check the excepted ones here??
        if item in hyperion_groups:
            hyperion_group = hyperion_nexus[item]
            gda_group = gda_nexus[item]
            print(hyperion_group, gda_group)
            assert isinstance(hyperion_group, Group) and isinstance(gda_group, Group)
            for dset_or_attr in hyperion_group:
                hyperion_item = mockitem("hyperion", dset_or_attr)
                gda_item = mockitem("gda", dset_or_attr)
                try:
                    hyperion_item = hyperion_group[dset_or_attr]
                except KeyError:
                    ...  # should probably correlate this with some key table
                try:
                    gda_item = gda_group[dset_or_attr]
                except KeyError:
                    ...  # should probably correlate this with some key table
                if not isinstance(hyperion_item, Group) and not isinstance(
                    hyperion_item, Datatype
                ):
                    assert not isinstance(gda_item, Group) and not isinstance(
                        gda_item, Datatype
                    )

                    hyperion_dtype = hyperion_item.dtype
                    gda_dtype = gda_item.dtype
                    print(
                        item,
                        dset_or_attr,
                        hyperion_dtype,
                        gda_dtype,
                        hyperion_dtype == gda_dtype,
                    )
                    if not hyperion_dtype == gda_dtype:
                        diffs[item + "/" + str(dset_or_attr)] = (
                            hyperion_dtype,
                            gda_dtype,
                        )
    print(diffs)


@pytest.mark.timeout(2)
def test_hyperion_vs_gda_datatypes(
    files_and_groups: FilesAndgroups,
):
    gda_nexus, gda_groups, hyperion_nexus, hyperion_groups = files_and_groups
    for item in gda_groups:
        # we checked separately if all expected items should be there
        # but we should probably still check the excepted ones here??
        if item in hyperion_groups:
            hyperion_group = hyperion_nexus[item]
            gda_group = gda_nexus[item]
            assert isinstance(hyperion_group, Group) and isinstance(gda_group, Group)
            for dset_or_attr in hyperion_group:
                hyperion_item = mockitem("hyperion", dset_or_attr)
                gda_item = mockitem("gda", dset_or_attr)
                try:
                    hyperion_item = hyperion_group[dset_or_attr]
                except KeyError:
                    ...  # should probably correlate this with some key table
                try:
                    gda_item = gda_group[dset_or_attr]
                except KeyError:
                    ...  # should probably correlate this with some key table
                if not isinstance(hyperion_item, Group) and not isinstance(
                    hyperion_item, Datatype
                ):
                    assert not isinstance(gda_item, Group) and not isinstance(
                        gda_item, Datatype
                    )
                    assert (
                        hyperion_item.dtype == gda_item.dtype
                        or DATATYPE_EXCEPTION_TABLE[item + "/" + str(dset_or_attr)]
                        == (hyperion_item.dtype, gda_item.dtype)
                    )


def _test_params(filename_stub, tmp_path: Path):
    def get_params(filename):
        with open(filename) as f:
            return json.loads(f.read())

    params = RotationScan(
        **raw_params_from_file(
            "tests/test_data/parameter_json_files/good_test_one_multi_rotation_scan_parameters.json",
            tmp_path,
        )
    )
    for scan_params in params.rotation_scans:
        scan_params.x_start_um = 0
        scan_params.y_start_um = 0
        scan_params.z_start_um = 0
        scan_params.scan_width_deg = 360
    params.file_name = filename_stub
    params.demand_energy_ev = 12700
    params.storage_directory = str(tmp_path)
    params.exposure_time_s = 0.004
    return params


def _generate_fake_nexus(
    filename,
    RE: RunEngine,
    rotation_scan_composite: RotationScanComposite,
    tmp_path: Path,
):
    params = _test_params(filename, tmp_path)
    run_number = params.detector_params.run_number
    filename_stub, run_number = sim_rotation_scan_to_create_nexus(
        params, rotation_scan_composite, filename, RE
    )
    return filename_stub, run_number


def sim_rotation_scan_to_create_nexus(
    test_params: RotationScan,
    fake_create_rotation_devices: RotationScanComposite,
    filename_stub,
    RE,
):
    run_number = test_params.detector_params.run_number
    nexus_filename = f"{filename_stub}_{run_number}.nxs"

    fake_create_rotation_devices.eiger.bit_depth.sim_put(32)  # type: ignore

    RE(
        fake_rotation_scan(
            test_params, RotationNexusFileCallback(), fake_create_rotation_devices
        )
    )

    nexus_path = Path(test_params.storage_directory) / nexus_filename
    assert os.path.isfile(nexus_path)
    return filename_stub, run_number


def fake_rotation_scan(
    parameters: RotationScan,
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
