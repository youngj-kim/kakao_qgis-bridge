"""Check real history import/query/delete behavior in a QGIS Python runtime."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch


def run(root):
    sys.path.insert(0, str(root))
    from kakao_qgis_bridge.plugin import KakaoQgisBridgePlugin
    from kakao_qgis_bridge.compat import MSGBOX_YES, MSGBOX_NO
    from qgis.core import Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsPointXY, QgsProject
    from qgis.gui import QgsMapCanvas

    app = QgsApplication([], False)
    app.initQgis()
    checks = []
    plugins = []

    def require(condition, message):
        if not condition:
            raise AssertionError(message)

    class Messages:
        def __init__(self):
            self.success = []
            self.info = []

        def pushSuccess(self, *args):
            self.success.append(args)

        def pushInfo(self, *args):
            self.info.append(args)

        def pushWarning(self, *args):
            pass

    class Iface:
        def __init__(self):
            self.canvas = QgsMapCanvas()
            self.canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
            self.messages = Messages()

        def mainWindow(self):
            return None

        def mapCanvas(self):
            return self.canvas

        def messageBar(self):
            return self.messages

    class Dock:
        web_view = None

        def set_center(self, *args):
            self.center = args

        def set_route_history(self, payload):
            self.history = payload

        def set_route_guidance(self, payload):
            self.guidance = payload

        def isVisible(self):
            return True

    def make_plugin():
        plugin = KakaoQgisBridgePlugin(Iface())
        plugins.append(plugin)
        return plugin

    def populate(plugin):
        for index in (1, 2):
            lon, lat = 127 + index / 100, 37.5
            guides = [dict(route_id=f"r{index}", sequence=seq, section_no=0, guide_type=1,
                           category="left", guidance="왼쪽 & 서울", name="도로", distance_m=100,
                           duration_s=20, cumulative_distance_m=100 * seq,
                           cumulative_duration_s=20 * seq, road_index=seq,
                           longitude=lon + seq / 1000, latitude=lat) for seq in (2, 1)]
            require(plugin.history_repository.append(
                f"h{index}", f"r{index}", f"2026-10-0{index}T00:00:00+09:00",
                [QgsPointXY(lon, lat), QgsPointXY(lon + .003, lat + .002)],
                (lon, lat), (lon + .003, lat + .002), "출발 서울", "도착 서울",
                [dict(lon=lon + .001, lat=lat, label="경유지")], 3500, 600, 2,
                "10분 · 3.5 km", "RECOMMEND", [],
                dict(car_type=1, car_fuel="GASOLINE", car_hipass=False), guides), "fixture failure")

    try:
        source = make_plugin()
        populate(source)
        require(source._route_feature_for_history("missing") is None, "missing route")
        require(source._guidance_features_for_history("missing") == [], "missing guides")
        copied = source._route_feature_for_history("h1")
        copied["origin_name"] = "changed"
        require(source._route_feature_for_history("h1")["origin_name"] == "출발 서울", "query aliases original")
        guides = source._guidance_features_for_history("h1")
        require([g["sequence"] for g in guides] == [1, 2], "guide order")
        guides[0]["guidance"] = "changed"
        require(source._guidance_features_for_history("h1")[0]["guidance"] == "왼쪽 & 서울", "guide aliases original")
        require([r["history_id"] for r in source._route_history_payload()["items"]] == ["h2", "h1"], "list order")
        checks.append("query copies, missing IDs, guide/list ordering")

        # Input restoration must reach both transports after controller extraction.
        source.dock = Mock()
        source.external_bridge_server = Mock()
        source._load_route_history("h1")
        script = source.dock.web_view.page.return_value.runJavaScript.call_args.args[0]
        require("window.loadRouteHistoryInput" in script and "waypoints" in script,
                "dock input restoration missing")
        signal, encoded = source.external_bridge_server.emit_signal.call_args.args
        require(signal == "loadRouteHistoryInput"
                and json.loads(encoded)["waypoints"][0]["label"] == "경유지",
                "external input restoration missing")
        source.dock.web_view.page.return_value.runJavaScript.reset_mock()
        source.external_bridge_server.emit_signal.reset_mock()
        source._load_route_history("missing")
        source.dock.web_view.page.return_value.runJavaScript.assert_not_called()
        source.external_bridge_server.emit_signal.assert_not_called()
        source.dock = None
        source.external_bridge_server = None
        checks.append("controller input restoration reaches both transports; missing ID ignored")

        from kakao_qgis_bridge.history_operations import HistoryOperationError
        info_count = len(source.iface.messages.info)
        with patch("kakao_qgis_bridge.plugin.QMessageBox.question", return_value=MSGBOX_YES), \
             patch.object(source.history_repository, "delete_history",
                          side_effect=HistoryOperationError("이력 삭제", "fixture failure")), \
             patch("kakao_qgis_bridge.plugin.QMessageBox.critical") as error:
            source._delete_route_history("h1")
        require(error.called and source.route_history_layer.featureCount() == 2,
                "failed deletion changed data or omitted error")
        require(len(source.iface.messages.info) == info_count,
                "failed deletion reported success")
        checks.append("controller deletion failure preserves data and omits success")

        with tempfile.TemporaryDirectory(prefix="kakao-history-", ignore_cleanup_errors=True) as directory:
            output = Path(directory)
            for suffix in (".gpkg", ".geojson", ".shp"):
                path = output / ("한글 이력" + suffix)
                if suffix == ".gpkg":
                    source._write_history_layer(source.route_history_layer, path, "kakao_route_history", "LineString")
                    source._write_history_layer(source.guidance_history_layer, path, "kakao_guidance_history", "Point")
                else:
                    rp, gp = source._paired_output_paths(path, suffix)
                    for layer, target, geometry, specs in (
                        (source.route_history_layer, rp, "LineString", source._route_shapefile_fields()),
                        (source.guidance_history_layer, gp, "Point", source._guidance_shapefile_fields())):
                        if suffix == ".geojson":
                            source._write_geojson_history_layer(layer, target, "history")
                        else:
                            source._write_shapefile_history_layer(layer, target, geometry, "history", specs)
                target = make_plugin()
                for run_index in (0, 1):
                    with patch("kakao_qgis_bridge.plugin.QFileDialog.getOpenFileName", return_value=(str(path), "")), \
                         patch("kakao_qgis_bridge.plugin.QMessageBox.critical", side_effect=lambda *args: (_ for _ in ()).throw(AssertionError(args[-1]))):
                        target._load_route_history_file()
                    require(target.route_history_layer.featureCount() == 2, "route import/dedup")
                    require(target.guidance_history_layer.featureCount() == 4, "guide import/dedup")
                    message = target.iface.messages.success[-1][-1]
                    require(("경로 2건" in message) if run_index == 0 else ("이미" in message), "import message")
                route = target._route_feature_for_history("h1")
                require(route["origin_name"] == "출발 서울" and route["distance_m"] == 3500, "route field mapping")
                points = target._route_points_from_geometry(route.geometry())
                require(abs(points[0].x() - 127.01) < 1e-7, "import geometry")
                require(target.route_history_layer.crs().authid() == "EPSG:4326", "import CRS")
                payload = target._route_input_payload_from_history(route)
                require(payload["waypoints"][0]["label"] == "경유지", "waypoints restore")
                require([g["sequence"] for g in target._guidance_features_for_history("h1")] == [1, 2], "import order")
                checks.append(suffix + ": import, fields, geometry, repeated import, input restore")

            target.dock = Dock()
            target._focus_route_history("h1")
            target.route_history_layer.selectAll()
            selected = target.route_history_layer.selectedFeatureIds()
            success_count = len(target.iface.messages.success)
            bad_routes, bad_guides = source._paired_output_paths(output / "invalid.geojson", ".geojson")
            source._write_geojson_history_layer(source.route_history_layer, bad_routes, "history")
            source._write_geojson_history_layer(source.guidance_history_layer, bad_guides, "history")
            invalid = json.loads(bad_routes.read_text(encoding="utf-8"))
            invalid["features"][0]["properties"]["schema_ver"] = 3
            bad_routes.write_text(json.dumps(invalid, ensure_ascii=False), encoding="utf-8")
            with patch("kakao_qgis_bridge.plugin.QFileDialog.getOpenFileName", return_value=(str(bad_routes), "")), \
                 patch("kakao_qgis_bridge.plugin.QMessageBox.critical") as error:
                target._load_route_history_file()
            require(error.called and "스키마" in error.call_args.args[-1], "invalid file error UI")
            require(target.active_route_history_id == "h1" and target.route_layer is not None,
                    "validation failure changed active display")
            require(target.route_history_layer.featureCount() == 2 and target.guidance_history_layer.featureCount() == 4
                    and target.route_history_layer.selectedFeatureIds() == selected
                    and len(target.iface.messages.success) == success_count, "validation failure changed data or success UI")
            checks.append("invalid file UI preserves data, selection and active route without success")

            # Empty paired GeoJSON is different from a repeated import.
            empty_path = output / "empty_routes.geojson"
            for suffix in ("routes", "guidance"):
                (output / f"empty_{suffix}.geojson").write_text(
                    json.dumps(dict(type="FeatureCollection", features=[])), encoding="utf-8")
            with patch("kakao_qgis_bridge.plugin.QFileDialog.getOpenFileName", return_value=(str(empty_path), "")):
                target._load_route_history_file()
            require("불러올 경로·안내 이력이 없습니다" in target.iface.messages.success[-1][-1],
                    "empty file misreported as already imported")
            require(target.active_route_history_id == "h1" and target.route_history_layer.featureCount() == 2
                    and target.route_history_layer.selectedFeatureIds() == selected,
                    "empty input changed existing history")
            repeat_routes, repeat_guides = source._paired_output_paths(output / "repeat.geojson", ".geojson")
            source._write_geojson_history_layer(source.route_history_layer, repeat_routes, "history")
            source._write_geojson_history_layer(source.guidance_history_layer, repeat_guides, "history")
            with patch("kakao_qgis_bridge.plugin.QFileDialog.getOpenFileName", return_value=(str(repeat_routes), "")):
                target._load_route_history_file()
            require("이미 현재 세션" in target.iface.messages.success[-1][-1], "repeated import message changed")
            checks.append("empty file distinguished from repeated import; existing data/selection preserved")

            target = make_plugin()
            count = len(target.iface.messages.success)
            with patch("kakao_qgis_bridge.plugin.QFileDialog.getOpenFileName", return_value=("", "")):
                target._load_route_history_file()
            require(target.route_history_layer is None and len(target.iface.messages.success) == count,
                    "cancel created data or reported success")
            # A paired file must be complete before the service creates targets.
            rp, _gp = source._paired_output_paths(output / "incomplete.geojson", ".geojson")
            source._write_geojson_history_layer(source.route_history_layer, rp, "history")
            with patch("kakao_qgis_bridge.plugin.QFileDialog.getOpenFileName", return_value=(str(rp), "")), \
                 patch("kakao_qgis_bridge.plugin.QMessageBox.critical") as error:
                target._load_route_history_file()
                require(error.called, "incomplete pair did not report failure")
            require(target.route_history_layer is None and len(target.iface.messages.success) == count,
                    "incomplete pair created data or reported success")
            checks.append("import cancellation and incomplete pair failure")

            gpx = output / "history.gpx"
            source._write_gpx_history(source.route_history_layer, source.guidance_history_layer, gpx)
            target = make_plugin()
            with patch("kakao_qgis_bridge.plugin.QFileDialog.getOpenFileName", return_value=(str(gpx), "")):
                target._load_styled_gpx()
            require(target.route_history_layer is None, "GPX unexpectedly imported session history")
            require("레이어 3개" in target.iface.messages.success[-1][-1], "GPX project load")
            checks.append("GPX styled project layers remain separate from session import")

        target = make_plugin()
        populate(target)
        actions = [Mock() for _ in range(4)]
        (target.save_history_action, target.export_geojson_action,
         target.export_shapefile_action, target.export_gpx_action) = actions
        target._update_history_action_state()
        require(all(action.setEnabled.call_args.args == (True,) for action in actions), "history actions disabled")
        target.dock = Dock()
        target._focus_route_history("h1")
        require(target.active_route_history_id == "h1" and target.route_layer is not None, "focus state")
        with patch("kakao_qgis_bridge.plugin.QMessageBox.question", return_value=MSGBOX_NO):
            target._delete_route_history("h1")
            target._delete_all_route_histories()
        require(target.route_history_layer.featureCount() == 2 and target.active_route_history_id == "h1", "cancel changed history")
        with patch("kakao_qgis_bridge.plugin.QMessageBox.question", return_value=MSGBOX_YES):
            target._delete_route_history("h2")
        require(target.active_route_history_id == "h1" and target.route_layer is not None, "inactive delete cleared display")
        require(target.guidance_history_layer.featureCount() == 2, "wrong guides deleted")
        with patch("kakao_qgis_bridge.plugin.QMessageBox.question", return_value=MSGBOX_YES):
            target._delete_route_history("h1")
        require(target.active_route_history_id is None and target.route_layer is None, "active delete kept display")
        require(target.dock.history["items"] == [] and target.dock.guidance["history_id"] == "", "delete kept viewer state")
        populate(target)
        target._focus_route_history("h2")
        with patch("kakao_qgis_bridge.plugin.QMessageBox.question", return_value=MSGBOX_YES):
            target._delete_all_route_histories()
        require(target.route_history_layer.featureCount() == 0 and target.guidance_history_layer.featureCount() == 0,
                "delete all left data")
        require(target.active_route_history_id is None and target.route_guidance_layer is None, "delete all kept display")
        require(all(action.setEnabled.call_args.args == (False,) for action in actions), "empty history actions enabled")
        with patch("kakao_qgis_bridge.plugin.QMessageBox.question") as dialog:
            target._delete_route_history("missing")
        require(not dialog.called, "missing ID prompted delete")
        checks.append("focus, deletion cancellation, inactive/active/all deletion, viewer updates")
        return dict(qgis_version=Qgis.QGIS_VERSION, status="ok", checks=checks)
    finally:
        for plugin in plugins:
            plugin.dock = None
            plugin._stop_external_bridge()
        QgsProject.instance().removeAllMapLayers()
        app.exitQgis()


if __name__ == "__main__":
    print("HISTORY_RESULT=" + json.dumps(run(Path(sys.argv[1]).resolve()), ensure_ascii=False))
