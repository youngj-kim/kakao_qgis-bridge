"""Recreate real plugin bridge sessions on a temporary port in QGIS Python."""
import http.client
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qgis.core import Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsRectangle
from qgis.gui import QgsMapCanvas
from kakao_qgis_bridge.plugin import KakaoQgisBridgePlugin
from kakao_qgis_bridge.external_bridge import KakaoExternalBridgeServer

app = QgsApplication([], False)
app.initQgis()
canvas = QgsMapCanvas()
canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
canvas.setExtent(QgsRectangle(14000000, 4400000, 14200000, 4600000))
iface = Mock()
iface.mapCanvas.return_value = canvas
iface.mainWindow.return_value = None
preferred = 0
old_token = None
results = []

def get(url, token):
    connection = http.client.HTTPConnection("127.0.0.1", urlsplit(url).port, timeout=2)
    try:
        connection.request("GET", "/api/state", headers={"X-Kakao-Bridge-Token": token})
        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()

for cycle in range(12):
    plugin = KakaoQgisBridgePlugin(iface)
    bridge = KakaoExternalBridgeServer(port=preferred, fallback_ports=(0,))
    try:
        with patch("kakao_qgis_bridge.plugin.KakaoExternalBridgeServer", return_value=bridge):
            plugin._ensure_external_bridge()
        assert plugin.external_bridge_server is bridge and bridge.url
        actual = urlsplit(bridge.url).port
        token = parse_qs(urlsplit(bridge.url).query)["token"][0]
        assert get(bridge.url, token) == 200
        if old_token is not None:
            assert token != old_token and get(bridge.url, old_token) == 403
        app.processEvents()
        results.append({"cycle": cycle, "same_port": preferred == 0 or actual == preferred})
        preferred, old_token = actual, token
    finally:
        plugin.unload()
        assert not plugin.external_bridge_timer.isActive()
        assert plugin.external_bridge_server is None and bridge._server is None
print("QGIS_RESTART_RESULT=" + json.dumps({"qgis": Qgis.QGIS_VERSION,
      "cycles": results, "status": "ok"}), flush=True)
