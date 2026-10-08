"""Observe current project transitions; no production changes or live API calls."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import Mock

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from qgis.core import Qgis, QgsApplication, QgsProject
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkReply
from kakao_qgis_bridge.plugin import KakaoQgisBridgePlugin
from kakao_qgis_bridge.external_bridge import KakaoExternalBridgeServer
from kakao_qgis_bridge.mobility import normalize_route_request, parse_route_payload


class FixtureReply(QObject):
    finished = pyqtSignal()

    def __init__(self, payload):
        super().__init__()
        self.payload = payload
        self.aborted = False

    def abort(self):
        self.aborted = True

    def attribute(self, _attribute):
        return 200

    def readAll(self):
        return json.dumps(self.payload).encode()

    def error(self):
        return QNetworkReply.NetworkError.NoError

    def errorString(self):
        return ""


app = QgsApplication([], False)
app.initQgis()
canvas = QgsMapCanvas()
iface = Mock()
iface.mapCanvas.return_value = canvas
iface.messageBar.return_value = Mock()
project = QgsProject.instance()
observations = []
fixture_path = root / "dist" / f"project-transition-review-{os.getpid()}.qgs"
assert not fixture_path.exists()
blank = QgsProject()
assert blank.write(str(fixture_path))
payload = dict(trans_id="fixture", routes=[dict(result_code=0,
    summary=dict(distance=1200, duration=180), sections=[dict(
        roads=[dict(vertexes=[126.9, 37.5, 127.0, 37.6])],
        guides=[dict(x=126.9, y=37.5, type=2, guidance="안내")])])])
request = normalize_route_request(126.9, 37.5, 127.0, 37.6, "RECOMMEND",
                                  "[]", "[]", "{}", "출발", "도착")
plugin = None
try:
    for transition in ("clear", "read"):
        project.clear()
        plugin = KakaoQgisBridgePlugin(iface)
        bridge = KakaoExternalBridgeServer(port=0)
        plugin.external_bridge_server = bridge  # In-memory snapshots; no server.
        plugin._handle_route_result(parse_route_payload(payload), request)
        active = plugin.active_route_history_id
        before_web = bridge.snapshot()["signals"]["routeGuidanceChanged"]
        reply = FixtureReply(payload)
        plugin.mobility_client._reply = reply
        reply.finished.connect(lambda: None)
        before_count = plugin.route_history_layer.featureCount()
        old_route = plugin.route_layer
        if transition == "clear":
            project.clear()
        else:
            assert project.read(str(fixture_path))
        try:
            old_route_valid = old_route.isValid()
        except RuntimeError:
            old_route_valid = False
        retained = dict(
            history_count=plugin.route_history_layer.featureCount(),
            active_history_retained=plugin.active_route_history_id == active,
            old_display_valid=old_route_valid,
            guidance_retained=bool(plugin._current_guidance_payload["path"]),
            web_snapshot_retained=bridge.snapshot()["signals"]["routeGuidanceChanged"] == before_web,
            pending_reply_retained=plugin.mobility_client._reply is reply,
            reply_aborted=reply.aborted)
        # Execute the real completion handler using a fixture reply, not a
        # network request. This emits the client's actual Qt success signal.
        plugin.mobility_client._handle_reply(reply, request)
        retained.update(late_reply_added_history=plugin.route_history_layer.featureCount() == before_count + 1,
                        late_reply_created_display=project.mapLayer(plugin.route_layer.id()) is not None)
        observations.append(dict(transition=transition, **retained))
        plugin.unload()
        plugin = None
    print("PROJECT_TRANSITION_REVIEW=" + json.dumps(dict(qgis=Qgis.QGIS_VERSION,
          observations=observations), ensure_ascii=False), flush=True)
finally:
    if plugin is not None:
        plugin.unload()
    project.clear()
    del blank
    fixture_path.unlink(missing_ok=True)
    fixture_path.with_suffix(".qgs~").unlink(missing_ok=True)
    app.exitQgis()
