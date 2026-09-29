import json
import os
import sys
import types
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen


qgis_module = types.ModuleType("qgis")
qgis_core_module = types.ModuleType("qgis.core")


class DummyQgsSettings:
    def value(self, _key, default=""):
        return default


qgis_core_module.QgsSettings = DummyQgsSettings
qgis_module.core = qgis_core_module
sys.modules.setdefault("qgis", qgis_module)
sys.modules.setdefault("qgis.core", qgis_core_module)
os.environ.setdefault("KAKAO_MAP_JAVASCRIPT_KEY", "test-javascript-key")

from kakao_qgis_bridge.external_bridge import KakaoExternalBridgeServer


class ExternalBridgeServerTest(unittest.TestCase):
    def setUp(self):
        self.server = KakaoExternalBridgeServer(port=0)
        self.viewer_url = self.server.start()
        parsed = urlsplit(self.viewer_url)
        self.origin = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
        self.token = parse_qs(parsed.query)["token"][0]

    def tearDown(self):
        self.server.stop()

    def request(self, path, *, token=None, payload=None, content_type=None):
        headers = {}
        data = None
        if token is not None:
            headers["X-Kakao-Bridge-Token"] = token
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = content_type or "application/json"
        request = Request(f"{self.origin}{path}", data=data, headers=headers)
        with urlopen(request, timeout=2) as response:
            return response.status, response.read()

    def request_with_headers(self, path, *, headers):
        request = Request(f"{self.origin}{path}", headers=headers)
        with urlopen(request, timeout=2) as response:
            return response.status, response.read()

    def test_viewer_requires_token(self):
        with self.assertRaises(HTTPError) as error:
            self.request("/")
        self.assertEqual(error.exception.code, 403)

        with urlopen(self.viewer_url, timeout=2) as response:
            document = response.read().decode("utf-8")
        self.assertIn("test-javascript-key", document)
        self.assertIn(self.token, document)
        self.assertIn("encodeURIComponent(bridgeToken)", document)

    def test_api_rejects_unauthorized_and_unknown_requests(self):
        with self.assertRaises(HTTPError) as error:
            self.request("/api/delete-all-route-histories", payload={})
        self.assertEqual(error.exception.code, 403)
        self.assertEqual(self.server.drain_events(), [])

        with self.assertRaises(HTTPError) as error:
            self.request("/api/not-supported", token=self.token, payload={})
        self.assertEqual(error.exception.code, 404)

    def test_authorized_event_is_queued(self):
        status, body = self.request(
            "/api/move-center",
            token=self.token,
            payload={"lon": 126.97, "lat": 37.56},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"ok": True})
        self.assertEqual(
            self.server.drain_events(),
            [
                {
                    "type": "move_center",
                    "payload": {"lon": 126.97, "lat": 37.56},
                }
            ],
        )

    def test_api_requires_json(self):
        with self.assertRaises(HTTPError) as error:
            self.request(
                "/api/move-center",
                token=self.token,
                payload={},
                content_type="text/plain",
            )
        self.assertEqual(error.exception.code, 415)
        self.assertEqual(self.server.drain_events(), [])

    def test_api_rejects_foreign_origin(self):
        with self.assertRaises(HTTPError) as error:
            self.request_with_headers(
                "/api/state",
                headers={
                    "X-Kakao-Bridge-Token": self.token,
                    "Origin": "https://example.invalid",
                },
            )
        self.assertEqual(error.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
