import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty, Queue

from .settings import PLUGIN_DIR, kakao_javascript_key


EXTERNAL_BRIDGE_SCRIPT = r"""
<script>
(() => {
  document.documentElement.classList.add("external-browser");

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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {})
      });
    } catch (error) {
      console.warn("Kakao QGIS external bridge request failed", path, error);
    }
  }

  async function pollState() {
    try {
      const response = await fetch("/api/state", { cache: "no-store" });
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
        cache: "no-store"
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
      window.open("/", "_blank", "noopener");
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


class KakaoExternalBridgeServer:
    def __init__(self, host="127.0.0.1", port=8081):
        self.host = host
        self.port = port
        self._server = None
        self._thread = None
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
        return f"http://localhost:{port}/"

    def start(self):
        if self._server is not None:
            return self.url

        handler = self._make_handler()
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
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

        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None

    def set_center(self, lon, lat):
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
        return html.replace(
            "__KAKAO_APP_KEY_JSON__",
            json.dumps(kakao_javascript_key()),
        )

    def _make_handler(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path in ("/", "/viewer"):
                    self._send_text(bridge._viewer_html(), "text/html")
                    return
                if self.path == "/api/state":
                    self._send_json({"center": bridge._center})
                    return
                if self.path.startswith("/api/events"):
                    since = 0
                    if "?since=" in self.path:
                        try:
                            since = int(self.path.rsplit("?since=", 1)[-1])
                        except ValueError:
                            since = 0
                    self._send_json(
                        {
                            "events": [
                                event
                                for event in bridge._outbound_events
                                if event["sequence"] > since
                            ]
                        }
                    )
                    return

                self.send_error(404)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    payload = {}

                event_type = self.path.rsplit("/", 1)[-1].replace("-", "_")
                bridge._events.put({"type": event_type, "payload": payload})
                self._send_json({"ok": True})

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
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def _send_json(self, payload):
                self._send_text(
                    json.dumps(payload, ensure_ascii=False),
                    "application/json",
                )

        return Handler
