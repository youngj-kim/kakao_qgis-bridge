import json
import hmac
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty, Queue
from urllib.parse import parse_qs, urlencode, urlsplit

from .settings import PLUGIN_DIR, kakao_javascript_key


EXTERNAL_BRIDGE_SCRIPT = r"""
<script>
(() => {
  document.documentElement.classList.add("external-browser");
  const bridgeToken = __KAKAO_BRIDGE_TOKEN_JSON__;

  const handlers = {
    routeStatusChanged: [],
    routeGuidanceChanged: [],
    routeHistoryChanged: [],
    loadRouteHistoryInput: []
  };
  let lastCenterSequence = -1;
  let lastEventSequence = 0;

  function signal(name) {
    return {
      connect(callback) {
        if (typeof callback === "function") {
          handlers[name].push(callback);
        }
      }
    };
  }

  async function post(path, payload) {
    try {
      await fetch(path, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Kakao-Bridge-Token": bridgeToken
        },
        body: JSON.stringify(payload || {})
      });
    } catch (error) {
      console.warn("Kakao QGIS external bridge request failed", path, error);
    }
  }

  async function pollState() {
    try {
      const response = await fetch("/api/state", {
        cache: "no-store",
        headers: { "X-Kakao-Bridge-Token": bridgeToken }
      });
      if (!response.ok) {
        return;
      }
      const state = await response.json();
      if (
        state.center &&
        state.center.sequence !== lastCenterSequence &&
        typeof window.centerKakaoMap === "function"
      ) {
        lastCenterSequence = state.center.sequence;
        window.centerKakaoMap(state.center.lon, state.center.lat);
      }
    } catch (error) {
      console.warn("Kakao QGIS external bridge state polling failed", error);
    }
  }

  async function pollEvents() {
    try {
      const response = await fetch(`/api/events?since=${lastEventSequence}`, {
        cache: "no-store",
        headers: { "X-Kakao-Bridge-Token": bridgeToken }
      });
      if (!response.ok) {
        return;
      }
      const payload = await response.json();
      for (const event of payload.events || []) {
        lastEventSequence = Math.max(lastEventSequence, event.sequence || 0);
        for (const callback of handlers[event.signal] || []) {
          callback(...(event.args || []));
        }
      }
    } catch (error) {
      console.warn("Kakao QGIS external bridge event polling failed", error);
    }
  }

  window.kakaoExternalBridge = {
    routeStatusChanged: signal("routeStatusChanged"),
    routeGuidanceChanged: signal("routeGuidanceChanged"),
    routeHistoryChanged: signal("routeHistoryChanged"),
    loadRouteHistoryInput: signal("loadRouteHistoryInput"),
    moveQgisCenter(lon, lat) {
      post("/api/move-center", { lon, lat });
    },
    updateRoadviewState(lon, lat, pan, tilt, zoom, pano_id) {
      post("/api/roadview-state", { lon, lat, pan, tilt, zoom, pano_id });
    },
    openKakaoRoadview(lon, lat) {
      window.open(
        `https://map.kakao.com/link/roadview/${lat.toFixed(8)},${lon.toFixed(8)}`,
        "_blank",
        "noopener"
      );
    },
    async toggleFullScreen() {
      const target = document.getElementById("viewer") || document.documentElement;
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else if (target.requestFullscreen) {
        await target.requestFullscreen();
      }
    },
    setRoutePoint(role, lon, lat) {
      post("/api/route-point", { role, lon, lat });
    },
    clearRoutePoint(role) {
      post("/api/clear-route-point", { role });
    },
    clearRoutePoints() {
      post("/api/clear-route-points", {});
    },
    selectRouteGuidance(sequence, lon, lat) {
      post("/api/select-route-guidance", { sequence, lon, lat });
    },
    selectRouteHistory(history_id) {
      post("/api/select-route-history", { history_id });
    },
    loadRouteHistoryFile() {
      post("/api/load-route-history-file", {});
    },
    loadRouteHistory(history_id) {
      post("/api/load-route-history", { history_id });
    },
    deleteRouteHistory(history_id) {
      post("/api/delete-route-history", { history_id });
    },
    deleteAllRouteHistories() {
      post("/api/delete-all-route-histories", {});
    },
    exportRouteHistory(history_id) {
      post("/api/export-route-history", { history_id });
    },
    exportRouteHistories(history_ids_json) {
      post("/api/export-route-histories", { history_ids_json });
    },
    refreshRouteHistory() {
      post("/api/refresh-route-history", {});
    },
    openExternalViewer() {
      window.open(
        `/?token=${encodeURIComponent(bridgeToken)}`,
        "_blank",
        "noopener"
      );
    },
    requestRoute(
      origin_lon,
      origin_lat,
      destination_lon,
      destination_lat,
      priority,
      waypoints_json,
      avoid_json,
      vehicle_json,
      origin_label,
      destination_label
    ) {
      post("/api/request-route", {
        origin_lon,
        origin_lat,
        destination_lon,
        destination_lat,
        priority,
        waypoints_json,
        avoid_json,
        vehicle_json,
        origin_label,
        destination_label
      });
    }
  };

  setInterval(pollState, 400);
  setInterval(pollEvents, 400);
  pollState();
  pollEvents();
})();
</script>
"""


MAX_REQUEST_BODY_BYTES = 64 * 1024
EXTERNAL_EVENT_PATHS = {
    "/api/move-center": "move_center",
    "/api/roadview-state": "roadview_state",
    "/api/request-route": "request_route",
    "/api/route-point": "route_point",
    "/api/clear-route-point": "clear_route_point",
    "/api/clear-route-points": "clear_route_points",
    "/api/select-route-guidance": "select_route_guidance",
    "/api/select-route-history": "select_route_history",
    "/api/load-route-history-file": "load_route_history_file",
    "/api/load-route-history": "load_route_history",
    "/api/delete-route-history": "delete_route_history",
    "/api/delete-all-route-histories": "delete_all_route_histories",
    "/api/export-route-history": "export_route_history",
    "/api/export-route-histories": "export_route_histories",
    "/api/refresh-route-history": "refresh_route_history",
}


class KakaoExternalBridgeServer:
    def __init__(self, host="127.0.0.1", port=8081):
        self.host = host
        self.port = port
        self._server = None
        self._thread = None
        self._token = secrets.token_urlsafe(32)
        self._viewer_document = ""
        self._state_lock = threading.Lock()
        self._events = Queue()
        self._outbound_events = []
        self._outbound_sequence = 0
        self._center = None
        self._center_sequence = 0

    @property
    def url(self):
        if self._server is None:
            return ""
        _host, port = self._server.server_address
        query = urlencode({"token": self._token})
        return f"http://localhost:{port}/?{query}"

    def start(self):
        if self._server is not None:
            return self.url

        # Render while still on the QGIS UI thread. QgsSettings and other Qt
        # backed objects must not be accessed by HTTP worker threads.
        self._viewer_document = self._viewer_html()
        handler = self._make_handler()
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="KakaoQgisExternalBridge",
            daemon=True,
        )
        self._thread.start()
        return self.url

    def stop(self):
        if self._server is None:
            return

        server = self._server
        thread = self._thread
        server.shutdown()
        server.server_close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._server = None
        self._thread = None
        self._viewer_document = ""

    def set_center(self, lon, lat):
        with self._state_lock:
            self._center_sequence += 1
            self._center = {
                "lon": float(lon),
                "lat": float(lat),
                "sequence": self._center_sequence,
            }

    def drain_events(self):
        events = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except Empty:
                return events

    def emit_signal(self, name, *args):
        with self._state_lock:
            self._outbound_sequence += 1
            self._outbound_events.append(
                {
                    "sequence": self._outbound_sequence,
                    "signal": name,
                    "args": list(args),
                }
            )
            if len(self._outbound_events) > 100:
                self._outbound_events = self._outbound_events[-100:]

    def _viewer_html(self):
        html = (PLUGIN_DIR / "web" / "kakao_viewer.html").read_text(
            encoding="utf-8"
        )
        html = html.replace(
            '<script src="qrc:///qtwebchannel/qwebchannel.js"></script>',
            EXTERNAL_BRIDGE_SCRIPT,
        )
        html = html.replace(
            "__KAKAO_BRIDGE_TOKEN_JSON__",
            json.dumps(self._token),
        )
        return html.replace(
            "__KAKAO_APP_KEY_JSON__",
            json.dumps(kakao_javascript_key()),
        )

    def _make_handler(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "KakaoQgisBridge"
            sys_version = ""

            def do_GET(self):
                parsed = urlsplit(self.path)
                if parsed.path in ("/", "/viewer"):
                    token = parse_qs(parsed.query).get("token", [""])[0]
                    if not self._authorized(token):
                        return
                    self._send_text(bridge._viewer_document, "text/html")
                    return
                if not self._authorized():
                    return
                if parsed.path == "/api/state":
                    with bridge._state_lock:
                        center = dict(bridge._center) if bridge._center else None
                    self._send_json({"center": center})
                    return
                if parsed.path == "/api/events":
                    since = 0
                    try:
                        since = int(parse_qs(parsed.query).get("since", ["0"])[0])
                    except ValueError:
                        since = 0
                    with bridge._state_lock:
                        events = [
                            dict(event)
                            for event in bridge._outbound_events
                            if event["sequence"] > since
                        ]
                    self._send_json(
                        {"events": events}
                    )
                    return

                self.send_error(404)

            def do_POST(self):
                parsed = urlsplit(self.path)
                try:
                    length = int(self.headers.get("Content-Length", "0") or "0")
                except ValueError:
                    self.send_error(400, "invalid Content-Length")
                    return
                if length < 0 or length > MAX_REQUEST_BODY_BYTES:
                    self.send_error(413, "request body too large")
                    return
                raw = self.rfile.read(length) if length else b"{}"

                event_type = EXTERNAL_EVENT_PATHS.get(parsed.path)
                if event_type is None:
                    self.send_error(404)
                    return
                if not self._authorized():
                    return
                if self.headers.get_content_type() != "application/json":
                    self.send_error(415, "application/json required")
                    return
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self.send_error(400, "invalid JSON")
                    return
                if not isinstance(payload, dict):
                    self.send_error(400, "JSON object required")
                    return

                bridge._events.put({"type": event_type, "payload": payload})
                self._send_json({"ok": True})

            def _authorized(self, token=""):
                _host, port = self.server.server_address
                expected_hosts = {f"localhost:{port}", f"127.0.0.1:{port}"}
                if self.headers.get("Host", "") not in expected_hosts:
                    self.send_error(403)
                    return False

                origin = self.headers.get("Origin", "")
                expected_origins = {
                    f"http://localhost:{port}",
                    f"http://127.0.0.1:{port}",
                }
                if origin and origin not in expected_origins:
                    self.send_error(403)
                    return False

                supplied_token = token or self.headers.get(
                    "X-Kakao-Bridge-Token",
                    "",
                )
                if not hmac.compare_digest(supplied_token, bridge._token):
                    self.send_error(403)
                    return False
                return True

            def log_message(self, _format, *_args):
                return

            def _send_text(self, body, content_type):
                encoded = body.encode("utf-8")
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    f"{content_type}; charset=utf-8",
                )
                self.send_header("Cache-Control", "no-store, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def _send_json(self, payload):
                self._send_text(
                    json.dumps(payload, ensure_ascii=False),
                    "application/json",
                )

        return Handler
