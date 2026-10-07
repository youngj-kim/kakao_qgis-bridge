"""Check viewer origins and event failure isolation with real Qt/QGIS canvases."""
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qgis.core import Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsPointXY, QgsRectangle
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QObject, pyqtSignal
from kakao_qgis_bridge.plugin import KakaoQgisBridgePlugin
from kakao_qgis_bridge.external_bridge import KakaoExternalBridgeServer


class DockSignals(QObject):
    centerRequested = pyqtSignal(float, float)


app = QgsApplication([], False)
app.initQgis()
canvas = QgsMapCanvas()
canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
canvas.setExtent(QgsRectangle(14000000, 4400000, 14200000, 4600000))
iface = Mock()
iface.mapCanvas.return_value = canvas
plugin = KakaoQgisBridgePlugin(iface)
signals = DockSignals()
dock = Mock()
dock.centerRequested = signals.centerRequested
dock.web_runtime_diagnostic = ""
dock.isVisible.return_value = True
with patch("kakao_qgis_bridge.plugin.KakaoMapDockWidget", return_value=dock), \
        patch("kakao_qgis_bridge.plugin.QTimer.singleShot"):
    plugin._ensure_dock()
server = KakaoExternalBridgeServer(port=0)
plugin.external_bridge_server = server
plugin.sync_controller.activate()
dock.set_center.reset_mock()

signals.centerRequested.emit(127.0, 37.0)
assert dock.set_center.call_count == 0, "dock received its own move"
center = server.snapshot()["center"]
assert abs(center["lon"] - 127.0) < 1e-7
assert center["source"] is None, "dock origin escaped into external client IDs"
json.dumps(server.snapshot())
assert not plugin.sync_controller.sync_timer.isActive(), "canvas echo was scheduled"

plugin._handle_viewer_moved(128.0, 38.0, source="dock")
assert dock.set_center.call_count == 1, "external client named dock collided with internal origin"
assert server.snapshot()["center"]["source"] == "dock"
current = canvas.center()
canvas.setCenter(QgsPointXY(current.x() + 1000, current.y() + 1000))
assert plugin.sync_controller.sync_timer.isActive(), "immediate user move was ignored"
plugin.sync_controller.sync_timer.stop()
plugin._sync_canvas_center()
assert dock.set_center.call_count == 2
assert server.snapshot()["center"]["source"] is None

def move(lon=129, source="normal"):
    return {"type": "move_center", "source": source,
            "payload": {"lon": lon, "lat": 37}}

with patch("kakao_qgis_bridge.plugin.QgsMessageLog.logMessage") as logs:
    # Actual queue: distinct origins prevent movement coalescing.
    assert server.queue_event(move(10**400, "bad"))
    assert server.queue_event(move())
    dock.set_center.reset_mock()
    plugin._process_external_bridge_events()
    assert dock.set_center.call_count == 1, "valid event after overflow was lost"
    assert abs(server.snapshot()["center"]["lon"] - 129) < 1e-7
    assert "OverflowError" in logs.call_args.args[0]
    assert not plugin._processing_external_bridge_events

    # Invalid event containers and handler errors stay within one event.
    batch = [None, {"type": "route_point", "payload": []},
             {"type": "clear_route_points", "payload": {}}, move(130)]
    with patch.object(server, "drain_events", return_value=batch), \
            patch.object(plugin, "_clear_route_points", side_effect=RecursionError("probe")):
        plugin._process_external_bridge_events()
    assert abs(server.snapshot()["center"]["lon"] - 130) < 1e-7
    assert not plugin._processing_external_bridge_events

    # A direct recursive dispatch leaves newly queued work for the next tick.
    clear = Mock()
    def dialog_callback():
        assert server.queue_event({"type": "clear_route_points", "payload": {}})
        plugin._process_external_bridge_events()
        assert not clear.called, "recursive dispatch drained queued work"
    with patch.object(plugin, "_delete_all_route_histories", side_effect=dialog_callback), \
            patch.object(plugin, "_clear_route_points", clear):
        server.queue_event({"type": "delete_all_route_histories", "payload": {}})
        plugin._process_external_bridge_events()
        assert not clear.called
        plugin._process_external_bridge_events()
        assert clear.call_count == 1
    assert not plugin._processing_external_bridge_events

    # Route failure is reported; even failure reporting cannot drop later work.
    request = {"type": "request_route", "payload": {
        "origin_lon": 127, "origin_lat": 37,
        "destination_lon": 128, "destination_lat": 38}}
    with patch.object(server, "drain_events", return_value=[request, move(131)]), \
            patch.object(plugin, "_request_route", side_effect=RecursionError("probe")), \
            patch.object(plugin, "_set_route_status") as status:
        plugin._process_external_bridge_events()
        assert status.call_count == 1 and status.call_args.args[0] is False
    with patch.object(server, "drain_events", return_value=[request, move(132)]), \
            patch.object(plugin, "_request_route", side_effect=RuntimeError("probe")), \
            patch.object(plugin, "_set_route_status", side_effect=RuntimeError("closed viewer")):
        plugin._process_external_bridge_events()
    assert abs(server.snapshot()["center"]["lon"] - 132) < 1e-7
    assert not plugin._processing_external_bridge_events

    # The guard also resets if draining itself fails.
    with patch.object(server, "drain_events", side_effect=RuntimeError("drain probe")):
        try:
            plugin._process_external_bridge_events()
        except RuntimeError:
            pass
        else:
            raise AssertionError("unexpected drain success")
    assert not plugin._processing_external_bridge_events

    # Work from a closed session is not applied after a dialog resumes.
    def close_callback():
        plugin.external_bridge_server = None
    with patch.object(server, "drain_events", return_value=[
            {"type": "delete_all_route_histories", "payload": {}}, move(133)]), \
            patch.object(plugin, "_delete_all_route_histories", side_effect=close_callback):
        plugin._process_external_bridge_events()
    assert abs(server.snapshot()["center"]["lon"] - 132) < 1e-7
    assert not plugin._processing_external_bridge_events

plugin.sync_controller.deactivate()
plugin.dock = None
print(json.dumps({"qgis": Qgis.QGIS_VERSION, "bridge_dispatch": "passed",
                  "checks": ["dock signal origin", "external fanout", "immediate canvas move",
                             "overflow isolation", "malformed event isolation", "handler exception",
                             "recursive guard", "route failure reporting", "guard recovery",
                             "closed session"]}))
