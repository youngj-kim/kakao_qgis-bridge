"""Exercise real history writers and reload their files under QGIS 3 and 4.

Run with the Python bundled with QGIS; no Kakao credentials or network needed.
"""
import json
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
from unittest.mock import patch


def run(root):
    sys.path.insert(0, str(root))
    from kakao_qgis_bridge.plugin import KakaoQgisBridgePlugin
    from qgis.core import Qgis, QgsApplication, QgsPointXY, QgsProject, QgsVectorLayer

    app = QgsApplication([], False)
    app.initQgis()
    plugin = KakaoQgisBridgePlugin(None)
    checks = []

    def require(condition, message):
        if not condition:
            raise AssertionError(message)

    def append(index):
        lon, lat = 127.0 + index / 100, 37.5
        guides = [dict(route_id=f"route-{index}", sequence=seq, section_no=0,
                       guide_type=1, category="left", guidance="서울 <왼쪽> & 진입",
                       name="도로 이름", distance_m=100, duration_s=20,
                       cumulative_distance_m=100 * seq, cumulative_duration_s=20 * seq,
                       road_index=seq, longitude=lon + seq / 1000, latitude=lat)
                  for seq in (2, 1)]
        require(plugin.history_repository.append(
            history_id=f"history-{index}", route_id=f"route-{index}",
            searched_at="2026-10-07T00:00:00+09:00",
            points=[QgsPointXY(lon, lat), QgsPointXY(lon + .003, lat + .002)],
            origin=(lon, lat), destination=(lon + .003, lat + .002),
            origin_label='출발 <서울> & "역"', destination_label="도착 한글",
            waypoints=[dict(lon=lon + .001, lat=lat, label="경유지")],
            distance=3500, duration=600, guidance_count=2, result_summary="10분 · 3.5 km",
            priority="RECOMMEND", avoid_options=[],
            vehicle_options=dict(car_type=1, car_fuel="GASOLINE", car_hipass=False),
            guides=guides), "fixture append failed")

    def reload(path, count, id_field="history_id", layer_name=None, qml=None):
        uri = str(path) + (f"|layername={layer_name}" if layer_name else "")
        layer = QgsVectorLayer(uri, "reload", "ogr")
        require(layer.isValid(), f"invalid layer: {uri}")
        require(layer.featureCount() == count, f"wrong count: {uri}")
        require(layer.crs().authid() == "EPSG:4326", f"wrong CRS: {uri}")
        require(all(not f.geometry().isEmpty() for f in layer.getFeatures()), "empty geometry")
        if id_field:
            require({str(f[id_field]) for f in layer.getFeatures()} == {"history-1", "history-2"},
                    f"history links lost: {uri}")
        if qml:
            require(qml.exists(), f"style missing: {qml}")
            error, ok = layer.loadNamedStyle(str(qml))
            require(ok, f"style load failed: {error}")
        return layer

    try:
        append(1)
        append(2)
        routes, guides = plugin.route_history_layer, plugin.guidance_history_layer
        with tempfile.TemporaryDirectory(prefix="kakao-export-", ignore_cleanup_errors=True) as directory:
            output = Path(directory)
            for suffix, writer in ((".geojson", plugin._write_geojson_history_layer),
                                   (".shp", plugin._write_shapefile_history_layer)):
                rp, gp = plugin._paired_output_paths(output / ("한글" + suffix), suffix)
                for layer, path, geometry, specs, count in (
                    (routes, rp, "LineString", plugin._route_shapefile_fields(), 2),
                    (guides, gp, "Point", plugin._guidance_shapefile_fields(), 4)):
                    args = (geometry, "history", specs) if suffix == ".shp" else ("history",)
                    require(writer(layer, path, *args) == count, "wrong writer count")
                    loaded = reload(path, count, "hist_id" if suffix == ".shp" else "history_id",
                                    qml=path.with_suffix(".qml"))
                    require(loaded.renderer().type() == layer.renderer().type(), "renderer changed")
                    if geometry == "LineString":
                        field = "org_name" if suffix == ".shp" else "origin_name"
                        require(next(loaded.getFeatures())[field] == '출발 <서울> & "역"', "text lost")
                        require(abs(plugin._route_points_from_geometry(next(loaded.getFeatures()).geometry())[0].x() - 127.01) < 1e-7,
                                "geometry changed")
                    else:
                        require(loaded.renderer().classAttribute() == "category", "style field lost")
                    if suffix == ".shp":
                        require(all(len(name) <= 10 for name in loaded.fields().names()), "long SHP field")
                    del loaded
                checks.append(suffix + ": data, fields, geometry, CRS, text, QML")

            path = output / "history.gpx"
            require(plugin._write_gpx_history(routes, guides, path) == (2, 4), "GPX counts")
            ns = {"g": "http://www.topografix.com/GPX/1/1", "k": "https://yjkim.dev/kakao-qgis-bridge"}
            tree = ET.parse(path).getroot()
            require(len(tree.findall("g:trk", ns)) == 2 and len(tree.findall("g:rte", ns)) == 2,
                    "GPX tracks/routes lost")
            waypoints = tree.findall("g:wpt", ns)
            require(len(waypoints) == 10, "GPX waypoints lost")
            require(waypoints[0].findtext("g:name", namespaces=ns) == '출발 <서울> & "역"', "XML text")
            require([w.findtext("g:extensions/k:sequence", namespaces=ns) for w in waypoints
                     if w.findtext("g:type", namespaces=ns) == "guidance:left"] == ["1", "2", "1", "2"],
                    "GPX guidance order")
            for name, count in (("tracks", 2), ("routes", 2), ("waypoints", 10)):
                loaded = reload(path, count, None, name, output / f"history_{name}.qml")
                require(loaded.renderer().type() == ("categorizedSymbol" if name == "waypoints"
                                                     else "singleSymbol"), "GPX renderer lost")
                del loaded
            checks.append(".gpx: XML, order, extensions, three layers and QML")

            path = output / "history.gpkg"
            for layer, name, geometry, count in ((routes, "kakao_route_history", "LineString", 2),
                                                  (guides, "kakao_guidance_history", "Point", 4)):
                require(plugin._write_history_layer(layer, path, name, geometry) == count, "GPKG count")
                require(plugin._write_history_layer(layer, path, name, geometry) == 0, "duplicate GPKG")
                loaded = reload(path, count, layer_name=name)
                require(loaded.renderer().type() == layer.renderer().type(), "GPKG default style")
                del loaded
            append(3)
            for layer, name, geometry, count in ((routes, "kakao_route_history", "LineString", 1),
                                                  (guides, "kakao_guidance_history", "Point", 2)):
                require(plugin._write_history_layer(layer, path, name, geometry) == count, "GPKG append")
                loaded = QgsVectorLayer(f"{path}|layername={name}", "reload", "ogr")
                require(loaded.featureCount() == (3 if geometry == "LineString" else 6), "GPKG total")
                del loaded
            checks.append(".gpkg: append, deduplication, linked layers, default styles")

            # Verify UI entry points use the same writers for selected histories.
            class Messages:
                def __init__(self):
                    self.success = []
                    self.warning = []

                def pushSuccess(self, *args):
                    self.success.append(args)

                def pushWarning(self, *args):
                    self.warning.append(args)

            class Iface:
                def __init__(self):
                    self.messages = Messages()

                def mainWindow(self):
                    return None

                def messageBar(self):
                    return self.messages

            plugin.iface = Iface()
            for label, extension in (("GeoPackage (*.gpkg)", ".gpkg"),
                                     ("GeoJSON (*.geojson)", ".geojson"),
                                     ("Shapefile (*.shp)", ".shp"), ("GPX (*.gpx)", ".gpx")):
                selected_path = output / ("selected" + extension)
                with patch("kakao_qgis_bridge.plugin.QInputDialog.getItem", return_value=(label, True)), \
                     patch("kakao_qgis_bridge.plugin.QFileDialog.getSaveFileName", return_value=(str(selected_path), label)):
                    plugin._export_route_histories(["history-2", "history-1", "history-2"], "selected", "test", "test")
                if extension in (".geojson", ".shp"):
                    rp, gp = plugin._paired_output_paths(selected_path, extension)
                    for p, count in ((rp, 2), (gp, 4)):
                        loaded = reload(p, count, "hist_id" if extension == ".shp" else "history_id")
                        del loaded
                elif extension == ".gpkg":
                    loaded = reload(selected_path, 2, layer_name="kakao_route_history")
                    del loaded
                    loaded = reload(selected_path, 4, layer_name="kakao_guidance_history")
                    del loaded
                else:
                    selected = ET.parse(selected_path).getroot()
                    require({t.findtext("g:extensions/k:history_id", namespaces=ns)
                             for t in selected.findall("g:trk", ns)} == {"history-1", "history-2"},
                            "selection leaked another history")
                require("경로 2건" in plugin.iface.messages.success[-1][-1], "selection count message")
            checks.append("selected UI: four formats, deduplication, history isolation")

            count = len(plugin.iface.messages.success)
            with patch("kakao_qgis_bridge.plugin.QInputDialog.getItem", return_value=("GPX (*.gpx)", False)), \
                 patch("kakao_qgis_bridge.plugin.QFileDialog.getSaveFileName") as dialog:
                plugin._export_route_histories(["history-1"], "cancel", "test", "test")
                require(not dialog.called, "cancel still opened save dialog")
            with patch("kakao_qgis_bridge.plugin.QFileDialog.getSaveFileName", return_value=("", "")):
                plugin._export_route_history_gpx()
            require(len(plugin.iface.messages.success) == count, "cancel reported success")
            with patch("kakao_qgis_bridge.plugin.QFileDialog.getSaveFileName",
                       return_value=(str(output / "failure.gpx"), "")), \
                 patch.object(plugin, "_write_gpx_history", side_effect=RuntimeError("expected failure")), \
                 patch("kakao_qgis_bridge.plugin.QMessageBox.critical") as error:
                plugin._export_route_history_gpx()
                require(error.called, "writer failure did not reach UI")
                require(len(plugin.iface.messages.success) == count, "failure reported success")
            checks.append("UI cancellation and writer failure")

            # A modal dialog must not resume an export across a project boundary.
            from kakao_qgis_bridge.compat import MSGBOX_YES, MSGBOX_NO

            def transition_result(result):
                plugin._project_epoch += 1
                return result

            count = len(plugin.iface.messages.success)
            with patch("kakao_qgis_bridge.plugin.QInputDialog.getItem",
                       side_effect=lambda *args: transition_result(("GPX (*.gpx)", True))), \
                 patch("kakao_qgis_bridge.plugin.QFileDialog.getSaveFileName") as dialog, \
                 patch.object(plugin, "_write_gpx_history") as writer:
                plugin._export_single_route_history("history-1")
                require(not dialog.called and not writer.called, "format transition resumed export")

            full_exports = (
                (plugin._save_route_history_geopackage, "_write_history_layer", ".gpkg"),
                (plugin._export_route_history_geojson, "_write_geojson_history_layer", ".geojson"),
                (plugin._export_route_history_shapefile, "_write_shapefile_history_layer", ".shp"),
                (plugin._export_route_history_gpx, "_write_gpx_history", ".gpx"),
            )
            for export, writer_name, extension in full_exports:
                target = output / ("boundary" + extension)
                with patch("kakao_qgis_bridge.plugin.QFileDialog.getSaveFileName",
                           side_effect=lambda *args: transition_result((str(target), ""))), \
                     patch.object(plugin, writer_name) as writer:
                    export()
                    require(not writer.called, "save transition resumed " + extension)

            for export, writer_name, extension in full_exports[1:]:
                target = output / ("overwrite" + extension)
                existing = (plugin._paired_output_paths(target, extension)[0]
                            if extension != ".gpx" else target)
                existing.write_bytes(b"existing-output")
                for answer, transition in ((MSGBOX_NO, False), (MSGBOX_YES, True)):
                    with patch("kakao_qgis_bridge.plugin.QFileDialog.getSaveFileName",
                               return_value=(str(target), "")), \
                         patch("kakao_qgis_bridge.plugin.QMessageBox.question",
                               side_effect=lambda *args: transition_result(answer) if transition else answer), \
                         patch.object(plugin, writer_name) as writer:
                        export()
                        require(not writer.called, "overwrite denial/transition resumed " + extension)
                        require(existing.read_bytes() == b"existing-output", "existing file changed")
            require(len(plugin.iface.messages.success) == count, "boundary cancellation reported success")

            with patch("kakao_qgis_bridge.plugin.QInputDialog.getItem") as dialog:
                for invalid in ('{"history_id": "history-1"}', '"history-1"', '123', 'null', 'broken'):
                    plugin._export_selected_route_histories(invalid)
                require(not dialog.called, "invalid selection reached export dialog")
            checks.append("UI project boundaries: format, four saves, three overwrite prompts; invalid selections")

            # UTF-8 may exceed the DBF limit before reaching 254 characters.
            feature = next(routes.getFeatures())
            long_name = "한" * 100
            long_waypoints = json.dumps([dict(lon=127.02, lat=37.5, label="경" * 100)], ensure_ascii=False)
            require(routes.dataProvider().changeAttributeValues({feature.id(): {
                routes.fields().indexOf("origin_name"): long_name,
                routes.fields().indexOf("waypoints_json"): long_waypoints,
            }}), "long text fixture failed")
            guide = next(guides.getFeatures())
            require(guides.dataProvider().changeAttributeValues({guide.id(): {
                guides.fields().indexOf("guidance"): "안" * 100,
            }}), "long guide fixture failed")
            def data(layer):
                return [(bytes(f.geometry().asWkb()), [str(v) for v in f.attributes()])
                        for f in layer.getFeatures()]
            before = (data(routes), data(guides))
            from kakao_qgis_bridge.history_export_service import HistoryExportService
            counts = HistoryExportService.shapefile_loss_counts(routes, plugin._route_shapefile_fields())
            require(counts == {"origin_name": 1, "waypoints_json": 1}, "byte loss detection")
            full = output / "long.shp"
            with patch("kakao_qgis_bridge.plugin.QFileDialog.getSaveFileName", return_value=(str(full), "")), \
                 patch("kakao_qgis_bridge.plugin.QgsMessageLog.logMessage") as logs:
                plugin._export_route_history_shapefile()
            require("전체 속성" in plugin.iface.messages.warning[-1][-1], "full SHP missing warning")
            require("waypoints_json 1건" in logs.call_args.args[0] and long_name not in logs.call_args.args[0],
                    "loss log must identify fields without original text")
            rp, gp = plugin._paired_output_paths(full, ".shp")
            loaded = reload(rp, 3, None)
            text = next(loaded.getFeatures())["org_name"]
            require(text == "한" * 84 and len(text.encode("utf-8")) <= 254, "UTF-8 SHP truncation")
            del loaded

            for hid, expected_warning in (("history-2", False), ("history-1", True)):
                warning_count = len(plugin.iface.messages.warning)
                selected_path = output / (hid + ".shp")
                with patch("kakao_qgis_bridge.plugin.QInputDialog.getItem", return_value=("Shapefile (*.shp)", True)), \
                     patch("kakao_qgis_bridge.plugin.QFileDialog.getSaveFileName", return_value=(str(selected_path), "")):
                    plugin._export_route_histories([hid], "selected", "test", "test")
                require(len(plugin.iface.messages.warning) - warning_count == int(expected_warning),
                        "SHP warning included unselected history or missed selected history")
            require((data(routes), data(guides)) == before, "SHP export modified source data")
            checks.append("SHP: byte-safe Korean text, full/selected warnings, affected counts, source preservation")

            require(routes.dataProvider().changeAttributeValues({feature.id(): {
                routes.fields().indexOf("origin_name"): "시작" + chr(1) + "역",
            }}), "GPX control fixture failed")
            require(guides.dataProvider().changeAttributeValues({guide.id(): {
                guides.fields().indexOf("guidance"): "좌" + chr(11) + "회전",
            }}), "GPX guidance control fixture failed")
            path = output / "controls.gpx"
            require(plugin._write_gpx_history(routes, guides, path) == (3, 6), "GPX control counts")
            ET.parse(path)
            text = path.read_text(encoding="utf-8")
            require(chr(1) not in text and chr(11) not in text and "시작역" in text and "좌회전" in text,
                    "GPX XML sanitization failed")
            require(next(routes.getFeatures())["origin_name"] == "시작" + chr(1) + "역",
                    "GPX export modified source data")
            checks.append("GPX: forbidden controls filtered in real writer, valid XML and source preserved")
        return dict(qgis_version=Qgis.QGIS_VERSION, checks=checks, status="ok")
    finally:
        QgsProject.instance().removeAllMapLayers()
        app.exitQgis()


if __name__ == "__main__":
    print("EXPORT_RESULT=" + json.dumps(run(Path(sys.argv[1]).resolve()), ensure_ascii=False))
