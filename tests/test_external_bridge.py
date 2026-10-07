import json
import errno
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import sys
import types
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, urlsplit
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
from kakao_qgis_bridge import external_bridge


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

    def test_non_ascii_tokens_are_rejected_and_server_stays_usable(self):
        for path in (f"/?token={quote('한글')}", f"/viewer?token={quote('ＡＢＣ')}"):
            with self.subTest(path=path):
                with self.assertRaises(HTTPError) as error:
                    self.request(path)
                self.assertEqual(error.exception.code, 403)
        # HTTP headers use Latin-1; this is still non-ASCII to compare_digest.
        with self.assertRaises(HTTPError) as error:
            self.request("/api/state", token="é")
        self.assertEqual(error.exception.code, 403)
        self.assertEqual(self.request("/api/state", token=self.token)[0], 200)
        self.assertEqual(self.server.drain_events(), [])

    def test_snapshot_and_cursor_recovery_over_http(self):
        self.server.set_center(127, 37.5, source="tab-a")
        self.server.emit_signal("routeGuidanceChanged", '{"path": [{"lon": 127, "lat": 37.5}]}')
        self.server.emit_signal("loadRouteHistoryInput", "old-input")
        state = json.loads(self.request("/api/state", token=self.token)[1])
        self.assertEqual(state["center"]["source"], "tab-a")
        self.assertIn("routeGuidanceChanged", state["signals"])
        self.assertNotIn("loadRouteHistoryInput", state["signals"])
        self.assertEqual(json.loads(self.request(
            f'/api/events?since={state["sequence"]}', token=self.token
        )[1])["events"], [])
        with patch.object(external_bridge, "MAX_OUTBOUND_EVENTS", 1):
            self.server.emit_signal("routeStatusChanged", True, "latest")
        recovery = json.loads(self.request("/api/events?since=0", token=self.token)[1])
        self.assertTrue(recovery["resync_required"])
        self.assertEqual(recovery["snapshot"]["signals"]["routeStatusChanged"]["args"], [True, "latest"])

    def test_invalid_cursor_and_overloaded_queue_have_explicit_status(self):
        for cursor in ("bad", "-1"):
            with self.subTest(cursor=cursor), self.assertRaises(HTTPError) as error:
                self.request(f"/api/events?since={cursor}", token=self.token)
            self.assertEqual(error.exception.code, 400)
        with patch.object(external_bridge, "MAX_PENDING_EVENTS", 0):
            with self.assertRaises(HTTPError) as error:
                self.request("/api/request-route", token=self.token, payload={})
            self.assertEqual(error.exception.code, 503)
        self.assertEqual(self.server.drain_events(), [])

    def test_source_identifier_is_preserved(self):
        request = Request(f"{self.origin}/api/move-center", data=b'{"lon": 127, "lat": 37.5}', headers={
            "Content-Type": "application/json", "X-Kakao-Bridge-Token": self.token,
            "X-Kakao-Bridge-Client": "tab-a",
        })
        with urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 200)
        self.assertEqual(self.server.drain_events()[0]["source"], "tab-a")

    def test_second_qgis_cannot_bind_to_same_port(self):
        port = urlsplit(self.viewer_url).port
        second = KakaoExternalBridgeServer(port=port)
        try:
            with self.assertRaises(OSError):
                second.start()
            self.assertEqual(second.url, "")
            self.assertEqual(self.request("/api/state", token=self.token)[0], 200)
        finally:
            second.stop()

    def test_existing_legacy_server_also_prevents_new_bridge_binding(self):
        legacy = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
        second = KakaoExternalBridgeServer(port=legacy.server_address[1])
        try:
            with self.assertRaises(OSError):
                second.start()
            self.assertEqual(second.url, "")
        finally:
            second.stop()
            legacy.server_close()

    def test_two_sessions_use_distinct_ports_and_keep_tokens_and_events_isolated(self):
        preferred = urlsplit(self.viewer_url).port
        second = KakaoExternalBridgeServer(port=preferred, fallback_ports=(0,))
        try:
            viewer_url = second.start()
            self.assertNotEqual(urlsplit(viewer_url).port, preferred)
            parsed = urlsplit(viewer_url)
            second_token = parse_qs(parsed.query)["token"][0]
            self.assertNotEqual(second_token, self.token)
            self.assertEqual(second.origin, f"http://localhost:{parsed.port}")
            with urlopen(viewer_url, timeout=2) as response:
                self.assertEqual(response.status, 200)
            wrong = Request(f"{second.origin}/api/state", headers={"X-Kakao-Bridge-Token": self.token})
            with self.assertRaises(HTTPError) as error:
                urlopen(wrong, timeout=2)
            self.assertEqual(error.exception.code, 403)
            command = Request(f"{second.origin}/api/move-center", data=b'{"lon": 127, "lat": 37.5}', headers={
                "X-Kakao-Bridge-Token": second_token, "Content-Type": "application/json",
                "Origin": second.origin,
            })
            with urlopen(command, timeout=2) as response:
                self.assertEqual(response.status, 200)
            self.assertEqual(len(second.drain_events()), 1)
            self.assertEqual(self.server.drain_events(), [])
            self.assertEqual(self.request("/api/state", token=self.token)[0], 200)
            self.assertEqual(second.start(), viewer_url)
        finally:
            second.stop()

    def test_all_candidate_ports_busy_returns_error_without_partial_server(self):
        busy = external_bridge.ExclusiveBridgeHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
        second = KakaoExternalBridgeServer(
            port=urlsplit(self.viewer_url).port, fallback_ports=(busy.server_address[1],)
        )
        try:
            with self.assertRaises(OSError):
                second.start()
            self.assertEqual(second.url, "")
            self.assertEqual(second.origin, "")
            self.assertEqual(self.request("/api/state", token=self.token)[0], 200)
        finally:
            second.stop()
            busy.server_close()


class BridgeStateTests(unittest.TestCase):
    def setUp(self):
        self.server = KakaoExternalBridgeServer(port=0)

    def test_unrelated_bind_failure_is_not_hidden_by_fallback(self):
        server = KakaoExternalBridgeServer(port=8081, fallback_ports=(8082,))
        with patch.object(external_bridge, "ExclusiveBridgeHTTPServer", side_effect=OSError(errno.EIO, "I/O failure")) as factory:
            with self.assertRaises(OSError):
                server.start()
            factory.assert_called_once()
        self.assertEqual(server.url, "")

    def test_new_tab_restores_latest_state_without_old_input_command(self):
        self.server.emit_signal("routeGuidanceChanged", "old-route")
        self.server.emit_signal("loadRouteHistoryInput", "old-input")
        self.server.emit_signal("routeGuidanceChanged", "active-route")
        self.server.emit_signal("routeHistoryChanged", "selected-history")
        self.server.set_center(127, 37.5, source="tab-a")
        state = self.server.snapshot()
        self.assertEqual(state["signals"]["routeGuidanceChanged"]["args"], ["active-route"])
        self.assertEqual(state["signals"]["routeHistoryChanged"]["args"], ["selected-history"])
        self.assertNotIn("loadRouteHistoryInput", state["signals"])
        self.server.emit_signal("loadRouteHistoryInput", "new-input")
        events = self.server.events_since(state["sequence"])
        self.assertFalse(events["resync_required"])
        self.assertEqual([event["args"] for event in events["events"]], [["new-input"]])

    def test_lagging_tab_gets_snapshot_when_events_are_evicted(self):
        with patch.object(external_bridge, "MAX_OUTBOUND_EVENTS", 2):
            for number in range(5):
                self.server.emit_signal("routeStatusChanged", True, str(number))
        self.assertEqual(len(self.server._outbound_events), 2)
        recovery = self.server.events_since(2)
        self.assertTrue(recovery["resync_required"])
        self.assertEqual(recovery["events"], [])
        self.assertEqual(recovery["snapshot"]["sequence"], 5)
        self.assertEqual(recovery["snapshot"]["signals"]["routeStatusChanged"]["args"], [True, "4"])
        self.assertFalse(self.server.events_since(3)["resync_required"])
        self.assertTrue(self.server.events_since(6)["resync_required"])

    def test_large_state_uses_snapshot_when_event_byte_limit_is_exceeded(self):
        with patch.object(external_bridge, "MAX_OUTBOUND_EVENT_BYTES", 64):
            self.server.emit_signal("routeGuidanceChanged", "route" * 100)
        self.assertEqual(len(self.server._outbound_events), 0)
        self.assertEqual(self.server._outbound_bytes, 0)
        recovery = self.server.events_since(0)
        self.assertTrue(recovery["resync_required"])
        self.assertEqual(recovery["snapshot"]["signals"]["routeGuidanceChanged"]["args"], ["route" * 100])

    def test_snapshot_and_events_do_not_expose_mutable_internal_state(self):
        value = {"path": [1, 2]}
        self.server.emit_signal("routeGuidanceChanged", value)
        value["path"].append(3)
        snapshot = self.server.snapshot()
        snapshot["signals"]["routeGuidanceChanged"]["args"][0]["path"].append(4)
        events = self.server.events_since(0)
        self.assertEqual(events["events"][0]["args"][0]["path"], [1, 2])
        events["events"][0]["args"][0]["path"].append(5)
        self.assertEqual(self.server.snapshot()["signals"]["routeGuidanceChanged"]["args"][0]["path"], [1, 2])

    def test_motion_updates_coalesce_per_source_without_crossing_commands(self):
        for source, lon in (("a", 1), ("b", 2), ("a", 3)):
            self.assertTrue(self.server.queue_event({"type": "move_center", "source": source, "payload": {"lon": lon}}))
        self.server.queue_event({"type": "request_route", "payload": {}})
        self.server.queue_event({"type": "move_center", "source": "a", "payload": {"lon": 4}})
        self.server.queue_event({"type": "move_center", "source": "a", "payload": {"lon": 5}})
        self.assertEqual(self.server.drain_events(), [
            {"type": "move_center", "source": "b", "payload": {"lon": 2}},
            {"type": "move_center", "source": "a", "payload": {"lon": 3}},
            {"type": "request_route", "payload": {}},
            {"type": "move_center", "source": "a", "payload": {"lon": 5}},
        ])
        self.assertEqual(self.server._pending_bytes, 0)

    def test_queue_limits_reject_commands_without_dropping_accepted_events(self):
        event = {"type": "move_center", "payload": {"lon": 1}}
        with patch.object(external_bridge, "MAX_PENDING_EVENTS", 1):
            self.assertTrue(self.server.queue_event(event))
            self.assertFalse(self.server.queue_event({"type": "request_route", "payload": {}}))
        with patch.object(external_bridge, "MAX_PENDING_EVENT_BYTES", 64):
            self.assertFalse(self.server.queue_event({"type": "move_center", "payload": {"text": "x" * 100}}))
        self.assertEqual(self.server.drain_events(), [event])


if __name__ == "__main__":
    unittest.main()
