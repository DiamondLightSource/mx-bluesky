from os.path import join
from pathlib import Path

TEST_DATA_PATH = Path(__file__).parent
TEST_OAV_CENTRING_JSON = join(TEST_DATA_PATH, "test_OAVCentring.json")
TEST_DISPLAY_CONFIG = join(TEST_DATA_PATH, "test_display.configuration")
TEST_OAV_ZOOM_LEVELS = join(TEST_DATA_PATH, "jCameraManZoomLevels.json")

__all__ = [
    "TEST_OAV_CENTRING_JSON",
    "TEST_DISPLAY_CONFIG",
    "TEST_OAV_ZOOM_LEVELS",
]
