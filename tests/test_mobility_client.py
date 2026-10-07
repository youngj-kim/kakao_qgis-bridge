"""Exercise the Qt adapter's failure/success paths with a fake network reply."""

import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from kakao_qgis_bridge.mobility import normalize_route_request


def load_client():
    core = types.ModuleType("qgis.PyQt.QtCore")
    class QObject:
        def __init__(self, parent=None):
            self.parent = parent
    core.QObject = QObject
    core.QTimer = MagicMock()
    core.QUrl = MagicMock()
    core.QUrlQuery = MagicMock()
    core.pyqtSignal = lambda *_args: MagicMock()
    network = types.ModuleType("qgis.PyQt.QtNetwork")
    network.QNetworkAccessManager = MagicMock()
    network.QNetworkReply = types.SimpleNamespace(
        NetworkError=types.SimpleNamespace(NoError=0)
    )
    network.QNetworkRequest = MagicMock()
    network.QNetworkRequest.Attribute.HttpStatusCodeAttribute = 1
    path = Path(__file__).resolve().parents[1] / "kakao_qgis_bridge" / "mobility_client.py"
    spec = importlib.util.spec_from_file_location("kakao_qgis_bridge._test_client", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"qgis.PyQt.QtCore": core,
                                  "qgis.PyQt.QtNetwork": network}):
        spec.loader.exec_module(module)
    return module


client_module = load_client()


class MobilityClientTests(unittest.TestCase):
    def setUp(self):
        self.client = client_module.MobilityClient()
        self.client.failed.reset_mock()
        self.client.succeeded.reset_mock()
        self.client._manager = MagicMock()
        self.request = normalize_route_request(
            126.9, 37.5, 127.0, 37.6, "RECOMMEND", "[]", "[]", "{}", "", ""
        )

    def reply(self, raw, status=200, network_error=0, timed_out=False):
        reply = MagicMock()
        reply.attribute.return_value = status
        reply.property.return_value = timed_out
        reply.readAll.return_value = raw
        reply.error.return_value = network_error
        reply.errorString.return_value = "network error"
        self.client._reply = reply
        return reply

    def test_invalid_key_emits_failure_without_sending_request(self):
        for key in ("전각키", "secret\nkey", "secret key", ""):
            with self.subTest(key=key):
                self.client.failed.reset_mock()
                self.client.request_route(key, self.request)
                self.client.failed.emit.assert_called_once()
                self.assertNotIn("secret", self.client.failed.emit.call_args.args[0])
                self.client._manager.get.assert_not_called()

    def test_malformed_success_response_emits_failure_and_releases_reply(self):
        for raw in (b"[]", b"null", b"not json", b"\xff", b""):
            with self.subTest(raw=raw):
                self.client.failed.reset_mock()
                reply = self.reply(raw)
                self.client._handle_reply(reply, self.request)
                self.client.failed.emit.assert_called_once()
                self.client.succeeded.emit.assert_not_called()
                reply.deleteLater.assert_called_once()
                self.assertIsNone(self.client._reply)

    def test_http_status_is_preserved_with_non_object_body(self):
        for status in (401, 403, 429):
            with self.subTest(status=status):
                self.client.failed.reset_mock()
                reply = self.reply(b"[]", status, network_error=1)
                self.client._handle_reply(reply, self.request)
                self.assertIn(str(status), self.client.failed.emit.call_args.args[0])
                self.client.succeeded.emit.assert_not_called()

    def test_timeout_keeps_specific_error_message(self):
        reply = self.reply(b"", None, network_error=1, timed_out=True)
        self.client._handle_reply(reply, self.request)
        self.assertIn("시간이 초과", self.client.failed.emit.call_args.args[0])

    def test_valid_response_emits_result_and_request(self):
        raw = json.dumps({"routes": [{
            "result_code": 0, "summary": {"distance": 1200, "duration": 180},
            "sections": [{"roads": [{"vertexes": [126.9, 37.5, 127.0, 37.6]}]}],
        }]}).encode("utf-8")
        reply = self.reply(raw)
        self.client._handle_reply(reply, self.request)
        self.client.failed.emit.assert_not_called()
        self.client.succeeded.emit.assert_called_once()
        result, request = self.client.succeeded.emit.call_args.args
        self.assertEqual(result.distance, 1200)
        self.assertIs(request, self.request)

    def test_stale_reply_cannot_replace_current_result(self):
        current = self.reply(b"[]")
        stale = MagicMock()
        self.client._handle_reply(stale, self.request)
        self.assertIs(self.client._reply, current)
        self.client.failed.emit.assert_not_called()
        self.client.succeeded.emit.assert_not_called()
        stale.deleteLater.assert_called_once()
