"""Real canvas coverage for zoom, pan, bridge fanout and feedback suppression."""
import json
import math
import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qgis.core import Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsPointXY, QgsRectangle
from qgis.gui import QgsMapCanvas
from kakao_qgis_bridge.plugin import KakaoQgisBridgePlugin
from kakao_qgis_bridge.dock_widget import KakaoWebBridge
from kakao_qgis_bridge.external_bridge import KakaoExternalBridgeServer

app = QgsApplication([], False)
app.initQgis()
canvas = QgsMapCanvas()
canvas.resize(800, 600)
canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:3857'))
canvas.setExtent(QgsRectangle(14130000, 4500000, 14132000, 4502000))
iface = Mock()
iface.mapCanvas.return_value = canvas
plugin = KakaoQgisBridgePlugin(iface)
plugin.dock = Mock()
plugin.dock.isVisible.return_value = True
server = KakaoExternalBridgeServer(port=0)
plugin.external_bridge_server = server
plugin.sync_controller.activate()
web_bridge = KakaoWebBridge()
web_bridge.zoomRequested.connect(plugin._handle_dock_viewer_zoomed)

try:
    # Embedded web bridge -> QGIS: ground resolution and center match, no echo.
    web_bridge.zoomQgisView(127, 37.5, 2.0)
    assert abs(plugin.sync_controller.meters_per_pixel() - 2) < 0.001
    lon, lat = plugin.sync_controller.to_wgs84(canvas.center())
    assert abs(lon - 127) < 1e-7 and abs(lat - 37.5) < 1e-7
    assert not plugin.sync_controller.sync_timer.isActive()
    assert server.snapshot()['center']['update_roadview'] is False
    # Same-center QGIS zoom must not be mistaken for the previous reverse echo.
    canvas.zoomByFactor(0.5)
    assert plugin.sync_controller.sync_timer.isActive()
    assert plugin.sync_controller.update_roadview is False
    plugin.sync_controller.sync_timer.stop()
    plugin.sync_controller.syncRequested.emit()
    view = server.snapshot()['center']
    assert abs(view['meters_per_pixel'] - 1) < 0.001
    assert plugin.dock.set_center.call_args.kwargs['update_roadview'] is False
    # A pan after zoom still moves all other maps and updates Roadview.
    center = canvas.center()
    canvas.setCenter(QgsPointXY(center.x() + 100, center.y() + 100))
    plugin.sync_controller.sync_timer.stop()
    plugin.sync_controller.syncRequested.emit()
    assert server.snapshot()['center']['update_roadview'] is True
    # External browser -> QGIS, preserving source and zoom-only policy.
    assert server.queue_event(dict(type='zoom_view', source='browser-a',
        payload=dict(lon=127.1, lat=37.6, meters_per_pixel=4)))
    plugin._process_external_bridge_events()
    assert abs(plugin.sync_controller.meters_per_pixel() - 4) < 0.001
    view = server.snapshot()['center']
    assert view['source'] == 'browser-a' and view['update_roadview'] is False
    # Invalid resolutions must not change either location or scale.
    before = QgsRectangle(canvas.extent())
    for invalid in (float('nan'), float('inf'), -1, 0, 1e20):
        plugin._handle_viewer_moved(129, 39, meters_per_pixel=invalid)
        assert canvas.extent() == before
    # A degree-based project also uses meters rather than raw CRS units.
    canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
    canvas.setExtent(QgsRectangle(126.99, 37.49, 127.01, 37.51))
    plugin._handle_dock_viewer_zoomed(127, 37.5, 3)
    assert abs(plugin.sync_controller.meters_per_pixel() - 3) < 0.001
    print('ZOOM_SYNC_RESULT=' + json.dumps(dict(status='ok', qgis=Qgis.QGIS_VERSION,
        checks=['dock zoom', 'QGIS zoom', 'pan after zoom', 'external zoom',
                'no feedback', 'invalid input', 'geographic CRS'])))
finally:
    plugin.dock = None
    plugin.external_bridge_server = None
    plugin.unload()
    canvas.deleteLater()
    app.exitQgis()
