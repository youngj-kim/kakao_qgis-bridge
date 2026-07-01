import json
import os
from pathlib import Path

from qgis.core import QgsSettings


PLUGIN_DIR = Path(__file__).resolve().parent
ENV_KAKAO_JS_KEY = "KAKAO_MAP_JAVASCRIPT_KEY"
ENV_KAKAO_REST_KEY = "KAKAO_REST_API_KEY"
SETTINGS_FILE = PLUGIN_DIR / "settings.json"
QGIS_KAKAO_JS_KEY = "kakao_qgis_bridge/kakao_javascript_key"
QGIS_KAKAO_REST_KEY = "kakao_qgis_bridge/kakao_rest_api_key"


def environment_javascript_key():
    return os.getenv(ENV_KAKAO_JS_KEY, "").strip()


def stored_javascript_key():
    value = QgsSettings().value(QGIS_KAKAO_JS_KEY, "")
    return str(value or "").strip()


def save_javascript_key(value):
    settings = QgsSettings()
    settings.setValue(QGIS_KAKAO_JS_KEY, str(value).strip())
    settings.sync()


def environment_rest_api_key():
    return os.getenv(ENV_KAKAO_REST_KEY, "").strip()


def stored_rest_api_key():
    value = QgsSettings().value(QGIS_KAKAO_REST_KEY, "")
    return str(value or "").strip()


def save_rest_api_key(value):
    settings = QgsSettings()
    settings.setValue(QGIS_KAKAO_REST_KEY, str(value).strip())
    settings.sync()


def kakao_rest_api_key():
    return environment_rest_api_key() or stored_rest_api_key()


def legacy_file_javascript_key():
    if not SETTINGS_FILE.exists():
        return ""

    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as handle:
            settings = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return ""

    return str(settings.get("kakao_javascript_key", "")).strip()


def kakao_javascript_key_source():
    if environment_javascript_key():
        return "environment"
    if stored_javascript_key():
        return "qgis"
    if legacy_file_javascript_key():
        return "file"
    return "missing"


def kakao_javascript_key():
    env_value = environment_javascript_key()
    if env_value:
        return env_value

    stored_value = stored_javascript_key()
    if stored_value:
        return stored_value

    return legacy_file_javascript_key()
