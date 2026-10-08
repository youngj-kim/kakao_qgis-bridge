import json
import hmac
import copy
import errno
import secrets
import socket
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

from .settings import PLUGIN_DIR, kakao_javascript_key
from .viewer_page import load_viewer_template


EXTERNAL_BRIDGE_SCRIPT = r"""
<script>
(() => {
  document.documentElement.classList.add("external-browser");
  const bridgeToken = __KAKAO_BRIDGE_TOKEN_JSON__;
  const clientId = window.crypto && typeof window.crypto.randomUUID === "function"
    ? window.crypto.randomUUID()
    : `viewer-${Date.now()}-${Math.random().toString(36).slice(2)}`;

  const handlers = {
    routeStatusChanged: [],
    routeGuidanceChanged: [],
    routeHistoryChanged: [],
    projectReset: [],
    loadRouteHistoryInput: []
  };
  let lastCenterSequence = -1;
  let lastEventSequence = null;
  let running = false;
  let pollTimer = null;
  let retryDelay = 400;

  function signal(name) {
    return {
      connect(callback) {
        if (typeof callback === "function") {
          handlers[name].push(callback);
        }
      }
    };
  }

  async function request(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(path, {
        ...options,
        signal: controller.signal,
        cache: "no-store",
        headers: {
          ...options.headers,
          "X-Kakao-Bridge-Token": bridgeToken,
          "X-Kakao-Bridge-Client": clientId
        }
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return await response.json();
    } finally {
      clearTimeout(timeout);
    }
  }

  async function post(path, payload) {
    try {
      await request(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {})
      });
    } catch (error) {
      const message = `QGIS 연결 요청에 실패했습니다 (${error.message}). 연결 상태를 확인한 뒤 다시 시도하세요.`;
      if (path === "/api/request-route") {
        dispatch("routeStatusChanged", [false, message]);
      } else if (typeof window.setKakaoBridgeStatus === "function") {
        window.setKakaoBridgeStatus(message);
      }
      console.warn("Kakao QGIS external bridge request failed", path, error);
    }
  }

  function dispatch(name, args) {
    for (const callback of handlers[name] || []) {
      callback(...args);
    }
  }

  function applyCenter(center, force = false) {
    if (!center || (!force && center.sequence === lastCenterSequence)) {
      return;
    }
    // This tab already applied its own drag. Other tabs must follow it.
    if ((force || center.source !== clientId) && typeof window.centerKakaoMap === "function") {
      window.centerKakaoMap(center.lon, center.lat);
    }
    lastCenterSequence = center.sequence;
  }

  function applySnapshot(state) {
    for (const name of ["projectReset", "routeGuidanceChanged", "routeHistoryChanged", "routeStatusChanged"]) {
      const event = (state.signals || {})[name];
      if (event) {
        dispatch(name, event.args || []);
      }
    }
    // Route rendering may fit bounds; apply the authoritative center last.
    applyCenter(state.center, true);
    lastEventSequence = state.sequence;
  }

  async function poll() {
    if (!running) {
      return;
    }
    try {
      if (lastEventSequence === null) {
        applySnapshot(await request("/api/state"));
      } else {
        const payload = await request(`/api/events?since=${lastEventSequence}`);
        if (payload.resync_required) {
          applySnapshot(payload.snapshot);
        } else {
          for (const event of payload.events || []) {
            if (event.sequence <= lastEventSequence) {
              continue;
            }
            if (event.signal === "centerChanged") {
              applyCenter(event.center);
            } else {
              dispatch(event.signal, event.args || []);
            }
            lastEventSequence = event.sequence;
          }
        }
      }
      retryDelay = 400;
    } catch (error) {
      retryDelay = Math.min(retryDelay * 2, 5000);
      console.warn("Kakao QGIS external bridge event polling failed", error);
    } finally {
      if (running) {
        pollTimer = setTimeout(poll, retryDelay);
      }
    }
  }

  window.kakaoExternalBridge = {
    start() {
      if (!running) {
        running = true;
        pollTimer = setTimeout(poll, 0);
      }
    },
    routeStatusChanged: signal("routeStatusChanged"),
    routeGuidanceChanged: signal("routeGuidanceChanged"),
    routeHistoryChanged: signal("routeHistoryChanged"),
    projectReset: signal("projectReset"),
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

})();
</script>
"""


MAX_REQUEST_BODY_BYTES = 64 * 1024
MAX_OUTBOUND_EVENTS = 100
MAX_OUTBOUND_EVENT_BYTES = 4 * 1024 * 1024
MAX_PENDING_EVENTS = 256
MAX_PENDING_EVENT_BYTES = 1024 * 1024
STATE_SIGNALS = {"routeStatusChanged", "routeGuidanceChanged", "routeHistoryChanged", "projectReset"}
TRANSIENT_SIGNALS = {"loadRouteHistoryInput"}
COALESCED_EVENTS = {"move_center", "roadview_state"}
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


class ExclusiveBridgeHTTPServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR permits duplicate binds and can route a tab to the
    # wrong QGIS session. Preserve ordinary restart behavior on other platforms.
    allow_reuse_address = not hasattr(socket, "SO_EXCLUSIVEADDRUSE")

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class KakaoExternalBridgeServer:
    def __init__(self, host="127.0.0.1", port=8081, fallback_ports=()):
        self.host = host
        self.port = port
        self._candidate_ports = tuple(dict.fromkeys((port, *fallback_ports)))
        self._server = None
        self._thread = None
        self._token = secrets.token_urlsafe(32)
        self._viewer_document = ""
        self._state_lock = threading.Lock()
        self._events = deque()
        self._event_lock = threading.Lock()
        self._pending_bytes = 0
        self._accepting_events = True
        self._project_epoch = 0
        self._outbound_events = deque()
        self._outbound_bytes = 0
        self._event_floor = 1
        self._signals = {}
        self._outbound_sequence = 0
        self._center = None

    @property
    def origin(self):
        if self._server is None:
            return ""
        _host, port = self._server.server_address
        return f"http://localhost:{port}"

    @property
    def url(self):
        if self._server is None:
            return ""
        query = urlencode({"token": self._token})
        return f"{self.origin}/?{query}"

    def start(self):
        if self._server is not None:
            return self.url

        # Render while still on the QGIS UI thread. QgsSettings and other Qt
        # backed objects must not be accessed by HTTP worker threads.
        self._viewer_document = self._viewer_html()
        handler = self._make_handler()
        for index, port in enumerate(self._candidate_ports):
            try:
                server = ExclusiveBridgeHTTPServer((self.host, port), handler)
            except OSError as exc:
                # An exclusive Windows bind can report WSAEACCES for an
                # occupied/reserved port. Do not hide unrelated I/O failures.
                occupied = exc.errno == errno.EADDRINUSE or getattr(exc, "winerror", None) in (10048, 10013)
                if not occupied or index == len(self._candidate_ports) - 1:
                    raise
            else:
                self._server = server
                break
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

    def set_center(self, lon, lat, source=None):
        with self._state_lock:
            self._outbound_sequence += 1
            self._center = {
                "lon": float(lon),
                "lat": float(lat),
                "sequence": self._outbound_sequence,
                "source": source,
            }
            self._retain_event({
                "sequence": self._outbound_sequence,
                "signal": "centerChanged",
                "center": dict(self._center),
            })

    def drain_events(self):
        with self._event_lock:
            events = [event for event, _size in self._events]
            self._events.clear()
            self._pending_bytes = 0
            return events

    def pause_events(self):
        with self._event_lock:
            self._project_epoch += 1
            self._accepting_events = False
            self._events.clear()
            self._pending_bytes = 0

    def reset_project_state(self):
        with self._state_lock:
            self._center = None
            self._signals.clear()
            self._outbound_events.clear()
            self._outbound_bytes = 0
            self._event_floor = self._outbound_sequence + 1

    def resume_events(self):
        with self._event_lock:
            self._accepting_events = True

    def queue_event(self, event):
        with self._event_lock:
            epoch = self._project_epoch
            if not self._accepting_events:
                return False
        event = copy.deepcopy(event)
        size = len(json.dumps(event, ensure_ascii=False).encode("utf-8"))
        with self._event_lock:
            if not self._accepting_events or epoch != self._project_epoch:
                return False
            replaced_index = None
            replaced_size = 0
            # Coalesce motion updates only after the last command barrier.
            if event["type"] in COALESCED_EVENTS:
                for index in range(len(self._events) - 1, -1, -1):
                    previous, previous_size = self._events[index]
                    if previous["type"] not in COALESCED_EVENTS:
                        break
                    if previous["type"] == event["type"] and previous.get("source") == event.get("source"):
                        replaced_index = index
                        replaced_size = previous_size
                        break
            pending_count = len(self._events) + (1 if replaced_index is None else 0)
            pending_bytes = self._pending_bytes - replaced_size + size
            if pending_count > MAX_PENDING_EVENTS or pending_bytes > MAX_PENDING_EVENT_BYTES:
                return False
            if replaced_index is not None:
                del self._events[replaced_index]
            self._events.append((event, size))
            self._pending_bytes = pending_bytes
            return True

    def emit_signal(self, name, *args):
        if name not in STATE_SIGNALS | TRANSIENT_SIGNALS:
            raise ValueError(f"Unsupported bridge signal: {name}")
        with self._state_lock:
            self._outbound_sequence += 1
            event = {
                "sequence": self._outbound_sequence,
                "signal": name,
                "args": copy.deepcopy(list(args)),
            }
            if name in STATE_SIGNALS:
                self._signals[name] = event
            self._retain_event(event)

    def _retain_event(self, event):
        """Called under _state_lock; an oversized event is restored by snapshot."""
        size = len(json.dumps(event, ensure_ascii=False).encode("utf-8"))
        self._outbound_events.append((event, size))
        self._outbound_bytes += size
        while len(self._outbound_events) > MAX_OUTBOUND_EVENTS or self._outbound_bytes > MAX_OUTBOUND_EVENT_BYTES:
            removed, removed_size = self._outbound_events.popleft()
            self._outbound_bytes -= removed_size
            self._event_floor = removed["sequence"] + 1

    def _snapshot_locked(self):
        return copy.deepcopy({
            "sequence": self._outbound_sequence,
            "center": self._center,
            "signals": self._signals,
        })

    def snapshot(self):
        with self._state_lock:
            return self._snapshot_locked()

    def events_since(self, since):
        with self._state_lock:
            resync = since < self._event_floor - 1 or since > self._outbound_sequence
            result = {
                "sequence": self._outbound_sequence,
                "resync_required": resync,
                "events": [] if resync else copy.deepcopy([
                    event for event, _size in self._outbound_events
                    if event["sequence"] > since
                ]),
            }
            if resync:
                result["snapshot"] = self._snapshot_locked()
            return result

    def _viewer_html(self):
        html = load_viewer_template(PLUGIN_DIR)
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
                    self._send_json(bridge.snapshot())
                    return
                if parsed.path == "/api/events":
                    try:
                        since = int(parse_qs(parsed.query).get("since", ["0"])[0])
                    except ValueError:
                        self.send_error(400, "invalid event cursor")
                        return
                    if since < 0:
                        self.send_error(400, "invalid event cursor")
                        return
                    self._send_json(bridge.events_since(since))
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

                event = {"type": event_type, "payload": payload}
                source = self.headers.get("X-Kakao-Bridge-Client", "")
                if source:
                    if len(source) > 64 or any(not (char.isascii() and (char.isalnum() or char in "-_")) for char in source):
                        self.send_error(400, "invalid client identifier")
                        return
                    event["source"] = source
                if not bridge.queue_event(event):
                    self.send_error(503, "bridge event queue is full")
                    return
                self._send_json({"ok": True})

            def _authorized(self, token=None):
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

                supplied_token = (
                    token
                    if token is not None
                    else self.headers.get("X-Kakao-Bridge-Token", "")
                )
                try:
                    supplied_token = supplied_token.encode("ascii")
                except UnicodeEncodeError:
                    self.send_error(403)
                    return False
                if not hmac.compare_digest(supplied_token, bridge._token.encode("ascii")):
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
