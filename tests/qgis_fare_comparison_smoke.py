"""Offline API-to-history-to-file-to-comparison checks for both plugins.

Pass the NAVER project path explicitly; no credentials or external requests.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from qgis.core import Qgis, QgsApplication, QgsProject, QgsVectorLayer, QgsVariantUtils
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtWidgets import QMainWindow
from qgis.PyQt.QtNetwork import QNetworkReply
from kakao_qgis_bridge.plugin import KakaoQgisBridgePlugin
from kakao_qgis_bridge.mobility import parse_route_payload, normalize_route_request
from kakao_qgis_bridge.route_comparison import read_routes
from kakao_qgis_bridge.route_comparison_dialog import RouteComparisonDialog
from kakao_qgis_bridge.history_import_service import HistoryImportService
from kakao_qgis_bridge.history_validation import HistoryValidationError
from navermap_qgis_bridge import classFactory

app = QgsApplication([], True)
app.initQgis()
window, canvas = QMainWindow(), QgsMapCanvas()
iface = Mock()
iface.mainWindow.return_value = window
iface.mapCanvas.return_value = canvas
kakao, naver = KakaoQgisBridgePlugin(iface), classFactory(iface)
request = normalize_route_request(127, 37, 127.1, 37.1, "RECOMMEND", "[]", "[]", "{}", "A", "B")
api = {"trans_id": "fare-test", "routes": [dict(result_code=0,
       summary=dict(distance=1200, duration=180, fare=dict(toll=0, taxi=10000)),
       sections=[dict(roads=[dict(vertexes=[127, 37, 127.1, 37.1])])])]}
kakao._handle_route_result(parse_route_payload(api), request)
source = next(kakao.route_history_layer.getFeatures())
assert (source["toll_fare"], source["taxi_fare"]) == (0, 10000)
naver_api = dict(code=0, route=dict(traoptimal=[dict(
    summary=dict(distance=1300, duration=190000, tollFare=1200, taxiFare=9500),
    path=[[127, 37], [127.1, 37.1]], guide=[])]))
reply = Mock()
naver.route_reply = reply
with patch("navermap_qgis_bridge.search_routes.read_reply", return_value=(
        200, json.dumps(naver_api).encode(), QNetworkReply.NetworkError.NoError, "")):
    naver._handle_route_reply(reply, "RECOMMEND", [], [],
        dict(car_type=1, car_fuel="gasoline", car_hipass=False),
        (127, 37), (127.1, 37.1), "A", "B")
assert naver.route_history_layer.featureCount() == 1
source_b = next(naver.route_history_layer.getFeatures())
assert (source_b["toll_fare"], source_b["taxi_fare"]) == (1200, 9500)
(root / "dist").mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="fare-comparison-", dir=root / "dist", ignore_cleanup_errors=True) as directory:
    paths = [Path(directory) / name for name in ("kakao.gpkg", "naver.gpkg")]
    gpx = Path(directory) / "kakao.gpx"
    kakao._write_gpx_history(kakao.route_history_layer, kakao.guidance_history_layer, gpx)
    tree = ET.parse(gpx)
    assert tree.findtext(".//{https://yjkim.dev/kakao-qgis-bridge}toll_fare") == "0"
    assert tree.findtext(".//{https://yjkim.dev/kakao-qgis-bridge}taxi_fare") == "10000"
    for plugin, path, table in zip((kakao, naver), paths, ("kakao_route_history", "naver_route_history")):
        assert plugin._write_history_layer(plugin.route_history_layer, path, table, "LineString") == 1
        # Verify the actual nullable integer fields in every supported vector output.
        for suffix in (".geojson", ".shp"):
            output = path.with_suffix(suffix)
            if suffix == ".shp":
                plugin._write_shapefile_history_layer(plugin.route_history_layer, output,
                    "LineString", "history", plugin._route_shapefile_fields())
            else:
                plugin._write_geojson_history_layer(plugin.route_history_layer, output, "history")
            layer = QgsVectorLayer(str(output), "reload", "ogr")
            assert layer.isValid()
            f = next(layer.getFeatures())
            original = next(plugin.route_history_layer.getFeatures())
            assert (f["toll_fare"], f["taxi_fare"]) == (original["toll_fare"], original["taxi_fare"])
            del layer
    rows = [read_routes(path) for path in paths]
    dialog = RouteComparisonDialog(iface)
    dialog.rows = rows
    for choice in dialog.choices:
        choice.blockSignals(True)
        choice.addItem("test")
        choice.blockSignals(False)
    dialog.refresh()
    assert dialog.table.rowCount() == 8
    assert dialog.table.item(6, 1).text() == "0원"
    assert dialog.table.item(6, 2).text() == "1,200원"
    assert dialog.table.item(7, 1).text() == "10,000원"
    assert "통행료 차이 (B − A): +1,200원" in dialog.conditions.text()
    assert "예상 택시요금 차이 (B − A): -500원" in dialog.conditions.text()
    dialog.show_routes()
    assert len(dialog.layer_ids) == 2
    # Old packages do not silently become free routes.
    saved = dict(dialog.rows[1][0]["values"])
    dialog.rows[1][0]["values"].pop("taxi_fare")
    dialog.refresh()
    assert dialog.table.item(7, 2).text() == "정보 없음"
    assert "예상 택시요금 차이 (B − A): 비교 불가" in dialog.conditions.text()
    dialog.rows[1][0]["values"] = saved
    dialog.dispose()
    # File import preserves nullable fares and rejects conflicts, rather than discarding them.
    kakao._write_history_layer(kakao.guidance_history_layer, paths[0], "kakao_guidance_history", "Point")
    restored = KakaoQgisBridgePlugin(iface)
    report = HistoryImportService(restored.history_repository).import_file(paths[0])
    assert report.routes == 1
    f = next(restored.route_history_layer.getFeatures())
    assert (f["toll_fare"], f["taxi_fare"]) == (0, 10000)
    # Same-ID fee changes must not be silently deduplicated as identical history.
    assert kakao.route_history_layer.dataProvider().changeAttributeValues({source.id(): {
        kakao.route_history_layer.fields().indexOf("taxi_fare"): 20000}})
    conflict = Path(directory) / "conflict.gpkg"
    kakao._write_history_layer(kakao.route_history_layer, conflict, "kakao_route_history", "LineString")
    kakao._write_history_layer(kakao.guidance_history_layer, conflict, "kakao_guidance_history", "Point")
    try:
        HistoryImportService(restored.history_repository).import_file(conflict)
        raise AssertionError("conflicting fare silently accepted")
    except HistoryValidationError:
        assert next(restored.route_history_layer.getFeatures())["taxi_fare"] == 10000
    # NULL fares survive actual vector file output instead of becoming free fares.
    legacy = KakaoQgisBridgePlugin(iface)
    api["routes"][0]["summary"].pop("fare")
    legacy._handle_route_result(parse_route_payload(api), request)
    for suffix in (".gpkg", ".geojson", ".shp"):
        unknown = Path(directory) / ("unknown" + suffix)
        if suffix == ".gpkg":
            legacy._write_history_layer(legacy.route_history_layer, unknown, "kakao_route_history", "LineString")
        elif suffix == ".shp":
            legacy._write_shapefile_history_layer(legacy.route_history_layer, unknown,
                "LineString", "history", legacy._route_shapefile_fields())
        else:
            legacy._write_geojson_history_layer(legacy.route_history_layer, unknown, "history")
        layer = QgsVectorLayer(str(unknown), "unknown", "ogr")
        f = next(layer.getFeatures())
        assert QgsVariantUtils.isNull(f["toll_fare"]) and QgsVariantUtils.isNull(f["taxi_fare"])
        del layer
print("FARE_COMPARISON_OK", Qgis.QGIS_VERSION, "API/history/GPKG/GeoJSON/SHP/import/UI; missing != zero")
QgsProject.instance().removeAllMapLayers()
canvas.deleteLater()
window.deleteLater()
app.processEvents()
