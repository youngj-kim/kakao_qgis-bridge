"""Exercise both providers, selection, map overlays and cleanup in real QGIS."""
import hashlib
import json
import math
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qgis.core import (Qgis, QgsApplication, QgsFeature, QgsGeometry, QgsPointXY,
                       QgsProject, QgsVectorFileWriter, QgsVectorLayer)
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtWidgets import QMainWindow
from kakao_qgis_bridge.route_comparison import read_routes, condition_message, display_layer, route_geometry
from kakao_qgis_bridge.route_comparison_dialog import RouteComparisonDialog

app = QgsApplication([], True)
app.initQgis()
from qgis.PyQt.QtGui import QFont, QFontDatabase
font_path = Path("C:/Windows/Fonts/malgun.ttf")
if font_path.exists():
    QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont("Malgun Gothic", 9))
fixture_parent = Path(__file__).resolve().parents[1] / "dist"
fixture_parent.mkdir(parents=True, exist_ok=True)
fixture_directory = tempfile.TemporaryDirectory(
    prefix="route-comparison-fixture-", dir=fixture_parent,
    ignore_cleanup_errors=True)
if len(sys.argv) > 1:
    source = Path(sys.argv[1])
else:
    source = Path(fixture_directory.name) / "naver.gpkg"
    layer = QgsVectorLayer("LineString?crs=EPSG:4326&field=history_id:string"
        "&field=origin_name:string&field=destination_name:string&field=searched_at:string"
        "&field=origin_lon:double&field=origin_lat:double&field=destination_lon:double"
        "&field=destination_lat:double&field=distance_m:double&field=duration_s:double"
        "&field=waypoints_json:string", "fixture", "memory")
    for index in range(2):
        feature = QgsFeature(layer.fields())
        feature.setAttributes([f"history-{index}", "출발", "도착", "2026-10-08",
                               127.0, 37.5, 127.01, 37.51, 1200 + index * 100, 180 + index * 30, "[]"])
        feature.setGeometry(QgsGeometry.fromPolylineXY(
            [QgsPointXY(127.0, 37.5), QgsPointXY(127.01, 37.51)]))
        assert layer.dataProvider().addFeatures([feature])[0]
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "naver_route_history"
    written = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(source), QgsProject.instance().transformContext(), options)
    assert written[0] == QgsVectorFileWriter.NoError, written
original = hashlib.sha256(source.read_bytes()).hexdigest()
naver = read_routes(source)
assert naver and all(row["provider"] == "네이버" for row in naver)
assert all('geometry' not in row for row in naver), 'list must not retain every route geometry'
assert all(set(row['values']) <= {'origin_lon', 'origin_lat', 'destination_lon', 'destination_lat',
    'origin_name', 'destination_name', 'searched_at', 'history_id', 'distance_m', 'duration_s',
    'waypoints_json'} for row in naver)
assert not route_geometry(naver[0]).isEmpty()

def waypoint_row(points):
    return dict(naver[0], values=dict(naver[0]['values'], waypoints_json=json.dumps(points)))

first = waypoint_row([dict(id='kakao:1', label='카카오', lon=127, lat=37)])
near = waypoint_row([dict(id='naver:99', label='다른 이름', lon=127.00001, lat=37)])
assert '경유지가 방문 순서별로 20m 이내' in condition_message(first, near)
assert '개수 불일치' in condition_message(first, waypoint_row([]))
ordered = [dict(lon=127, lat=37), dict(lon=128, lat=38)]
assert '20m 초과' in condition_message(waypoint_row(ordered), waypoint_row(list(reversed(ordered))))
equator = waypoint_row([dict(lon=0, lat=0)])
for metres, expected in ((19.9, '20m 이내'), (20, '20m 이내'), (20.1, '20m 초과')):
    point = dict(lon=0, lat=metres / 6371008.8 * 180 / math.pi)
    assert expected in condition_message(equator, waypoint_row([point]))
for invalid in (None, {}, [None], [dict(lon=True, lat=37)], [dict(lon=float('nan'), lat=37)],
                [dict(lon=181, lat=37)], [dict(lon=127, lat=91)], [dict(lon=127)]):
    assert '경유지 정보를 확인할 수 없습니다' in condition_message(first, waypoint_row(invalid))
assert '두 경로 모두 경유지가 없습니다' in condition_message(waypoint_row([]), waypoint_row([]))
for label, style in (('B로 이름을 바꾼 A', 'solid'), ('A로 이름을 바꾼 B', 'dash')):
    overlay = display_layer(naver[0], label, '35,110,230', line_style=style)
    assert overlay.customProperty('skipMemoryLayersCheck') == 1
    assert overlay.renderer().symbol().symbolLayer(0).properties()['line_style'] == style
del overlay
# A changed source must not silently pair stale summary with a different geometry.
changed_package = Path(fixture_directory.name) / 'changed.gpkg'
changed_package.write_bytes(source.read_bytes())
indexed = read_routes(changed_package)
stat = changed_package.stat()
os.utime(changed_package, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
try:
    route_geometry(indexed[0])
    raise AssertionError('changed package accepted')
except ValueError as exc:
    assert '다시 여세요' in str(exc)
# Geometry validation is deferred until the selected route is displayed.
empty_package = Path(fixture_directory.name) / 'empty-geometry.gpkg'
empty_layer = QgsVectorLayer('LineString?crs=EPSG:4326&field=origin_lon:double'
    '&field=origin_lat:double&field=destination_lon:double&field=destination_lat:double',
    'empty fixture', 'memory')
empty_feature = QgsFeature(empty_layer.fields())
empty_feature.setAttributes([127, 37, 127.1, 37.1])
assert empty_layer.dataProvider().addFeatures([empty_feature])[0]
empty_options = QgsVectorFileWriter.SaveVectorOptions()
empty_options.driverName = 'GPKG'
empty_options.layerName = 'kakao_route_history'
assert QgsVectorFileWriter.writeAsVectorFormatV3(empty_layer, str(empty_package),
    QgsProject.instance().transformContext(), empty_options)[0] == QgsVectorFileWriter.NoError
empty_rows = read_routes(empty_package)
assert len(empty_rows) == 1 and 'geometry' not in empty_rows[0]
try:
    route_geometry(empty_rows[0])
    raise AssertionError('empty geometry accepted')
except ValueError as exc:
    assert '유효한 경로 선' in str(exc)

class Iface:
    def __init__(self):
        self.window = QMainWindow()
        self.canvas = QgsMapCanvas()

    def mainWindow(self):
        return self.window

    def mapCanvas(self):
        return self.canvas

    def addToolBarIcon(self, *_):
        pass

    def addPluginToMenu(self, *_):
        pass

    def removePluginMenu(self, *_):
        pass

    def removeToolBarIcon(self, *_):
        pass

with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1], ignore_cleanup_errors=True) as directory:
    # Build a minimal Kakao package with the same real route geometry and fields.
    package = Path(directory) / "kakao.gpkg"
    with sqlite3.connect(source.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as db:
        with sqlite3.connect(package) as output:
            db.backup(output)
    with sqlite3.connect(package) as db:
        db.execute('ALTER TABLE naver_route_history RENAME TO kakao_route_history')
        db.execute("UPDATE gpkg_contents SET table_name='kakao_route_history' WHERE table_name='naver_route_history'")
        db.execute("UPDATE gpkg_geometry_columns SET table_name='kakao_route_history' WHERE table_name='naver_route_history'")
    kakao = read_routes(package)
    assert kakao[0]["provider"] == "카카오"
    assert "20m 이내" in condition_message(naver[0], kakao[0])
    changed = dict(kakao[0], values=dict(kakao[0]["values"], origin_lon=128))
    assert "출발·도착지가 다릅니다" in condition_message(naver[0], changed)
    iface = Iface()
    dialog = RouteComparisonDialog(iface)
    assert not dialog.show_button.isEnabled()
    dialog.rows = [naver, kakao]
    for choice in dialog.choices:
        choice.blockSignals(True)
        choice.addItem("test")
        choice.blockSignals(False)
    dialog.refresh()
    assert dialog.show_button.isEnabled()
    assert "B − A" in dialog.conditions.text()
    dialog.show()
    app.processEvents()
    if len(sys.argv) > 2:
        dialog.grab().save(sys.argv[2])
    dialog.show_routes()
    assert len(dialog.layer_ids) == 2
    assert all(QgsProject.instance().mapLayer(i).featureCount() == 1 for i in dialog.layer_ids)
    assert all(QgsProject.instance().mapLayer(i).customProperty('skipMemoryLayersCheck') == 1
               for i in dialog.layer_ids)
    dialog.show_routes()
    assert len(QgsProject.instance().mapLayers()) == 2
    dialog.refresh()
    assert not QgsProject.instance().mapLayers()
    if len(naver) > 1:
        dialog.choices[0].addItem("second")
        dialog.show_routes()
        dialog.choices[0].setCurrentIndex(1)
        assert not dialog.layer_ids
    dialog.show_routes()
    QgsProject.instance().clear()
    assert not dialog.layer_ids
    dialog.show_routes()
    dialog.dispose()
    assert not QgsProject.instance().mapLayers()
    from kakao_qgis_bridge.plugin import KakaoQgisBridgePlugin
    plugin = KakaoQgisBridgePlugin(iface)
    plugin.initGui()
    plugin.compare_routes_action.trigger()
    assert plugin.comparison_dialog is not None
    plugin._open_route_comparison()
    comparison = plugin.comparison_dialog
    assert plugin.comparison_dialog is comparison
    plugin.unload()
    assert plugin.comparison_dialog is None and plugin.compare_routes_action is None
assert hashlib.sha256(source.read_bytes()).hexdigest() == original
print(f"ROUTE_COMPARISON_OK ({Qgis.QGIS_VERSION}): providers, conditions, selection, overlays, menu/unload, source unchanged", flush=True)
iface.canvas.setLayers([])
iface.canvas.deleteLater()
iface.window.deleteLater()
app.processEvents()
fixture_directory.cleanup()
