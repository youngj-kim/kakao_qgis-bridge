import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from kakao_qgis_bridge.mobility import RouteValidationError


core = types.ModuleType("qgis.core")
core.QgsSettings = MagicMock()
path = Path(__file__).resolve().parents[1] / "kakao_qgis_bridge" / "settings.py"
spec = importlib.util.spec_from_file_location("kakao_qgis_bridge._test_settings", path)
settings = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"qgis.core": core}):
    spec.loader.exec_module(settings)


class RestKeySettingsTests(unittest.TestCase):
    def setUp(self):
        core.QgsSettings.reset_mock()

    def test_invalid_key_does_not_modify_stored_settings(self):
        for key in ("전각키", "key with space", "key\nvalue", ""):
            with self.subTest(key=key):
                with self.assertRaises(RouteValidationError):
                    settings.save_rest_api_key(key)
                core.QgsSettings.assert_not_called()

    def test_valid_key_is_trimmed_and_saved(self):
        settings.save_rest_api_key("  ascii-key123  ")
        store = core.QgsSettings.return_value
        store.setValue.assert_called_once_with(settings.QGIS_KAKAO_REST_KEY, "ascii-key123")
        store.sync.assert_called_once()
