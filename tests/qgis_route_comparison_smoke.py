"""Exercise both providers, selection, map overlays and cleanup in real QGIS."""
import hashlib
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qgis.core import (Qgis, QgsApplication, QgsFeature, QgsGeometry, QgsPointXY,
                       QgsProject, QgsVectorFileWriter, QgsVectorLayer)
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtWidgets import QMainWindow
from kakao_qgis_bridge.route_comparison import read_routes, condition_message
from kakao_qgis_bridge.route_comparison_dialog import RouteComparisonDialog

app = QgsApplication([], True)
app.initQgis()
from qgis.PyQt.QtGui import QFont, QFontDatabase
font_path = Path("C:/Windows/Fonts/malgun.ttf")
if font_path.exists():
    QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont("Malgun Gothic", 9))
fixture_directory = tempfile.TemporaryDirectory(
    prefix="route-comparison-fixture-", dir=Path(__file__).resolve().parents[1] / "dist",
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
