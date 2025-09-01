from ophyd_async.core import AutoIncrementFilenameProvider, StaticPathProvider
from ophyd_async.fastcs.jungfrau import Jungfrau

from mx_bluesky.beamlines.i24.jungfrau_commissioning.plan_utils import (
    override_file_name_and_path,
)


def test_override_file_name_and_path(
    jungfrau: Jungfrau,
    tmpdir,
):
    test_path = f"{tmpdir}/test_file"
    override_file_name_and_path(jungfrau, test_path)
    real_path_provider = jungfrau._writer._path_provider
    assert isinstance(real_path_provider, StaticPathProvider)
    assert isinstance(
        real_path_provider._filename_provider,
        AutoIncrementFilenameProvider,
    )
    assert real_path_provider._filename_provider._base_filename == "test_file"
    assert (real_path_provider._directory_path) == tmpdir
