"""Read-only probes for review claims; observations are not pass/fail tests."""
import json
import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, Qgis
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QTimer, QEventLoop
from kakao_qgis_bridge.plugin import KakaoQgisBridgePlugin

app = QgsApplication([], False)
app.initQgis()
canvas = QgsMapCanvas()
canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
iface = Mock()
iface.mapCanvas.return_value = canvas
plugin = KakaoQgisBridgePlugin(iface)
dock = Mock()
dock.isVisible.return_value = True
plugin.dock = dock
plugin._handle_dock_viewer_moved(127.0, 37.0)
result = {"qgis": Qgis.QGIS_VERSION,
          "dock_self_echo_calls": dock.set_center.call_count}

events = [{"type": "move_center", "payload": {"lon": 10**400, "lat": 37}},
          {"type": "move_center", "payload": {"lon": 128, "lat": 38}}]
bridge = Mock()
bridge.drain_events.side_effect = lambda: [events.pop(0) for _ in range(len(events))]
plugin.external_bridge_server = bridge
dock.set_center.reset_mock()
try:
    plugin._process_external_bridge_events()
except Exception as exc:
    result["batch_exception"] = type(exc).__name__
result["remaining_queued_events"] = len(events)
result["valid_following_event_processed"] = bool(dock.set_center.call_count)

timer = QTimer()
state = {"depth": 0, "max_depth": 0, "calls": 0}
def tick():
    state["depth"] += 1
    state["max_depth"] = max(state["max_depth"], state["depth"])
    state["calls"] += 1
    if state["calls"] == 1:
        nested = QEventLoop()
        QTimer.singleShot(100, nested.quit)
        nested.exec()
        timer.stop()
    state["depth"] -= 1
timer.timeout.connect(tick)
timer.start(10)
outer = QEventLoop()
QTimer.singleShot(180, outer.quit)
outer.exec()
result["same_timer_nested_loop"] = state
crs84 = QgsCoordinateReferenceSystem("OGC:CRS84")
result["crs84"] = {"valid": crs84.isValid(), "authid": crs84.authid(),
                   "equals_4326": crs84 == QgsCoordinateReferenceSystem("EPSG:4326")}
print(json.dumps(result))
plugin.external_bridge_server = None
plugin.dock = None
plugin.sync_controller.deactivate()
