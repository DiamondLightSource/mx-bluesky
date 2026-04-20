from unittest.mock import MagicMock, patch

from bluesky.plan_stubs import null
from bluesky.run_engine import RunEngine
from ophyd_async.fastcs.panda import HDFPanda

from mx_bluesky.common.device_setup_plans.setup_panda import load_panda_from_yaml


def get_test_plan(*args):
    yield from null()
    return "retrieved_settings"


@patch("mx_bluesky.common.device_setup_plans.setup_panda.YamlSettingsProvider")
@patch("mx_bluesky.common.device_setup_plans.setup_panda.retrieve_settings")
@patch("mx_bluesky.common.device_setup_plans.setup_panda.apply_panda_settings")
def test_load_panda_from_yaml(
    mock_apply_panda_settings: MagicMock,
    mock_retrieve_settings: MagicMock,
    mock_settings_provider: MagicMock,
    panda: HDFPanda,
    tmpdir,
    RE: RunEngine,
):
    test_file = "test"
    mock_settings_provider.return_value = (mock_settings_return := MagicMock())
    mock_retrieve_settings.side_effect = get_test_plan

    RE(
        load_panda_from_yaml(
            tmpdir,
            test_file,
            panda,
        )
    )

    mock_settings_provider.assert_called_once_with(tmpdir)
    mock_retrieve_settings.assert_called_once_with(
        mock_settings_return, test_file, panda
    )
    mock_apply_panda_settings.assert_called_once_with("retrieved_settings")
