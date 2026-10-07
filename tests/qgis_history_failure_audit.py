"""Check refused edits, partial changes and recovery using real QGIS providers.

Originally reproduced unchecked failures; now checks the corrected behavior.
All files and mutations belong to temporary fixtures, never a user's project.
"""
import csv
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from unittest.mock import patch


def run(root):
    sys.path.insert(0, str(root))
    from kakao_qgis_bridge.plugin import KakaoQgisBridgePlugin
    from kakao_qgis_bridge.compat import MSGBOX_YES
    from kakao_qgis_bridge.history_operations import HistoryOperationError
    from kakao_qgis_bridge.mobility import RouteRequestData, RouteResultData
    from qgis.core import Qgis, QgsApplication, QgsGeometry, QgsProject, QgsPointXY, QgsVectorLayer
    from history_key_reference import reference_key
    from qgis.PyQt.QtCore import QUrl
    from qgis.gui import QgsMapCanvas

    app = QgsApplication([], False)
    app.initQgis()
    observations = []

    def require(condition, message):
        if not condition:
            raise AssertionError(message)

    class Messages:
        def __init__(self):
            self.success = []
            self.info = []
            self.warnings = []

        def pushSuccess(self, *args):
            self.success.append(args[-1])

        def pushInfo(self, *args):
            self.info.append(args[-1])

        def pushWarning(self, *args):
            self.warnings.append(args[-1])

    class Iface:
        def __init__(self):
            self.messages = Messages()

        def mainWindow(self):
            return None

        def messageBar(self):
            return self.messages

        def mapCanvas(self):
            if not hasattr(self, "canvas"):
                self.canvas = QgsMapCanvas()
            return self.canvas

    def fixture(index):
        return dict(history_id=f"h{index}", route_id=f"r{index}", searched_at="2026-10-07",
                    points=[QgsPointXY(127, 37.5), QgsPointXY(127.003, 37.502)],
                    origin=(127, 37.5), destination=(127.003, 37.502),
                    origin_label="출발", destination_label="도착", waypoints=[], distance=3500,
                    duration=600, guidance_count=1, result_summary="경로", priority="RECOMMEND",
                    avoid_options=[], vehicle_options=dict(car_type=1, car_fuel="GASOLINE", car_hipass=False),
                    guides=[dict(route_id=f"r{index}", sequence=1, section_no=0, guide_type=1,
                                 category="left", guidance="좌회전", name="도로", distance_m=100,
                                 duration_s=20, cumulative_distance_m=100, cumulative_duration_s=20,
                                 road_index=0, longitude=127.001, latitude=37.501)])

    def plugin_with_history(index):
        plugin = KakaoQgisBridgePlugin(Iface())
        require(plugin.history_repository.append(**fixture(index)), "fixture append failed")
        return plugin

    def read_only_copy(layer, path, geometry_type):
        fields = layer.fields().names()
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=[*fields, "geom_wkt"])
            writer.writeheader()
            for feature in layer.getFeatures():
                writer.writerow({**{name: feature[name] for name in fields},
                                 "geom_wkt": feature.geometry().asWkt()})
        uri = QUrl.fromLocalFile(str(path)).toString()
        uri += f"?type=csv&detectTypes=yes&wktField=geom_wkt&geomType={geometry_type}&crs=EPSG:4326"
        result = QgsVectorLayer(uri, "read-only audit fixture", "delimitedtext")
        require(result.isValid() and result.featureCount() == 1, "read-only fixture invalid")
        feature = next(result.getFeatures())
        before = result.featureCount()
        add_result = result.dataProvider().addFeature(feature)
        delete_result = result.dataProvider().deleteFeatures([feature.id()])
        require(not add_result and not delete_result and result.featureCount() == before,
                "fixture provider did not actually refuse edits")
        return result

    try:
        with tempfile.TemporaryDirectory(prefix="kakao-failure-audit-", ignore_cleanup_errors=True) as directory:
            output = Path(directory)
            seed = plugin_with_history(1)
            readonly_route = read_only_copy(seed.route_history_layer, output / "routes.csv", "line")
            readonly_guide = read_only_copy(seed.guidance_history_layer, output / "guides.csv", "point")

            # Read-only targets must fail before either target is changed.
            plugin = KakaoQgisBridgePlugin(Iface())
            plugin._ensure_route_history_layers()
            plugin.guidance_history_layer = readonly_guide
            try:
                plugin.history_repository.append(**fixture(2))
                raise AssertionError("read-only guide accepted")
            except HistoryOperationError as exc:
                require(exc.recovered, "preflight marked partial change")
            require(plugin._route_feature_for_history("h2") is None, "preflight changed route")
            observations.append(dict(case="read_only_append", status="blocked before changes"))

            # Use a real GPKG source, real read-only route target and writable guide target.
            source = plugin_with_history(2)
            gpkg = output / "incoming.gpkg"
            source._write_history_layer(source.route_history_layer, gpkg, "kakao_route_history", "LineString")
            source._write_history_layer(source.guidance_history_layer, gpkg, "kakao_guidance_history", "Point")
            plugin = KakaoQgisBridgePlugin(Iface())
            plugin._ensure_route_history_layers()
            plugin.route_history_layer = readonly_route
            with patch("kakao_qgis_bridge.plugin.QFileDialog.getOpenFileName", return_value=(str(gpkg), "")), \
                 patch("kakao_qgis_bridge.plugin.QMessageBox.critical") as error:
                plugin._load_route_history_file()
                require(error.called, "import failed without error UI")
            require(plugin._route_feature_for_history("h2") is None
                    and not plugin._guidance_features_for_history("h2")
                    and not plugin.iface.messages.success, "failed import changed data or reported success")
            observations.append(dict(case="read_only_import", status="no data added, error UI"))

            # Failed deletion keeps both data and active UI state.
            plugin = plugin_with_history(1)
            plugin.route_history_layer = readonly_route
            plugin.active_route_history_id = "h1"
            with patch("kakao_qgis_bridge.plugin.QMessageBox.question", return_value=MSGBOX_YES), \
                 patch("kakao_qgis_bridge.plugin.QMessageBox.critical") as error:
                plugin._delete_route_history("h1")
                require(error.called, "delete failed without error UI")
            require(plugin._route_feature_for_history("h1") is not None
                    and len(plugin._guidance_features_for_history("h1")) == 1
                    and plugin.active_route_history_id == "h1" and not plugin.iface.messages.info,
                    "failed deletion changed state or reported success")
            observations.append(dict(case="read_only_delete_one", status="data and active history preserved"))

            plugin = plugin_with_history(1)
            plugin.guidance_history_layer = readonly_guide
            with patch("kakao_qgis_bridge.plugin.QMessageBox.question", return_value=MSGBOX_YES), \
                 patch("kakao_qgis_bridge.plugin.QMessageBox.critical"):
                plugin._delete_all_route_histories()
            require(plugin.route_history_layer.featureCount() == 1
                    and plugin.guidance_history_layer.featureCount() == 1
                    and not plugin.iface.messages.info, "failed delete-all changed data")
            observations.append(dict(case="read_only_delete_all", status="both layers preserved"))

            # These hooks perform actual edits before failing. Inspect real data,
            # not only mocked return values, after compensating recovery.
            def contents(repo):
                return [Counter(reference_key(feature) for feature in layer.getFeatures())
                        for layer in (repo.route_layer, repo.guidance_layer)]

            for mode in ("false_before", "false_partial", "false_full", "exception_partial", "true_missing"):
                plugin = plugin_with_history(1)
                repo = plugin.history_repository
                before = contents(repo)
                original_add = repo._operations._provider_add
                request = fixture(2)
                request["guides"].append({**request["guides"][0], "sequence": 2})
                request["guidance_count"] = 2

                def failing_add(layer, features):
                    if layer is repo.guidance_layer:
                        if mode == "true_missing":
                            return True, []
                        if mode != "false_before":
                            original_add(layer, features if mode == "false_full" else features[:1])
                        if mode == "exception_partial":
                            raise RuntimeError("injected after real partial add")
                        return False, []
                    return original_add(layer, features)

                with patch.object(repo._operations, "_provider_add", side_effect=failing_add):
                    try:
                        repo.append(**request)
                        raise AssertionError("injected add accepted")
                    except HistoryOperationError as exc:
                        require(exc.recovered, "add recovery failed: " + mode)
                require(contents(repo) == before and not repo.needs_recovery, "add changed original data: " + mode)
                observations.append(dict(case="add_" + mode, status="original data recovered"))

            # Successful provider return values and unchanged IDs/counts must
            # not conceal a change to an existing row during an append.
            for corruption in ("attributes", "geometry"):
                plugin = plugin_with_history(1)
                repo = plugin.history_repository
                before = contents(repo)
                layers = (repo.route_layer, repo.guidance_layer)
                for layer in layers:
                    layer.selectByIds([next(layer.getFeatures()).id()])
                selected_before = [Counter(reference_key(f) for f in layer.selectedFeatures())
                                   for layer in layers]
                old = repo.route_for_history("h1")
                original_add = repo._operations._provider_add
                injected = [False]

                def corrupting_add(layer, features):
                    result = original_add(layer, features)
                    if layer is repo.route_layer and not injected[0]:
                        injected[0] = True
                        if corruption == "attributes":
                            changed = layer.dataProvider().changeAttributeValues({old.id(): {
                                layer.fields().indexOf("origin_name"): "corrupted"}})
                        else:
                            points = old.geometry().asPolyline()
                            points[0] = QgsPointXY(points[0].x() + 1e-9, points[0].y())
                            geometry = QgsGeometry.fromPolylineXY(points)
                            require(bytes(geometry.asWkb()) != bytes(old.geometry().asWkb()),
                                    "geometry probe did not change WKB")
                            changed = layer.dataProvider().changeGeometryValues({old.id(): geometry})
                        require(changed, "corruption provider edit failed")
                    return result

                with patch.object(repo._operations, "_provider_add", side_effect=corrupting_add):
                    try:
                        repo.append(**fixture(2))
                        raise AssertionError("existing corruption accepted: " + corruption)
                    except HistoryOperationError as exc:
                        require(exc.recovered, "corruption recovery failed: " + corruption)
                require(contents(repo) == before and not repo.needs_recovery,
                        "corruption changed original data: " + corruption)
                require([Counter(reference_key(f) for f in layer.selectedFeatures())
                         for layer in layers] == selected_before, "corruption recovery lost selection")
                observations.append(dict(case="add_existing_" + corruption + "_changed",
                                         status="detected, data and selection recovered"))

            for operation in ("one", "all"):
                plugin = plugin_with_history(1)
                repo = plugin.history_repository
                before = contents(repo)
                repo.route_layer.selectByIds([repo.route_for_history("h1").id()])
                repo.guidance_layer.selectByIds([repo.guidance_for_history("h1")[0].id()])
                original_delete = repo._operations._provider_delete

                def failing_delete(layer, ids):
                    result = original_delete(layer, ids)
                    return False if layer is repo.guidance_layer else result

                with patch.object(repo._operations, "_provider_delete", side_effect=failing_delete):
                    try:
                        repo.delete_history("h1") if operation == "one" else repo.delete_all()
                        raise AssertionError("injected delete accepted")
                    except HistoryOperationError as exc:
                        require(exc.recovered, "delete recovery failed")
                require(contents(repo) == before, "delete recovery changed attributes/geometry")
                require(all(layer.selectedFeatureCount() == 1 for layer in (repo.route_layer, repo.guidance_layer)),
                        "re-added feature selection lost")
                observations.append(dict(case="delete_" + operation, status="data and selection recovered"))

            # Real import: route write succeeds, guide write fails, both undo.
            plugin = plugin_with_history(1)
            repo = plugin.history_repository
            before = contents(repo)
            original_add = repo._operations._provider_add

            def fail_import_guide(layer, features):
                return (False, []) if layer is repo.guidance_layer else original_add(layer, features)

            with patch.object(repo._operations, "_provider_add", side_effect=fail_import_guide), \
                 patch("kakao_qgis_bridge.plugin.QFileDialog.getOpenFileName", return_value=(str(gpkg), "")), \
                 patch("kakao_qgis_bridge.plugin.QMessageBox.critical") as error:
                plugin._load_route_history_file()
                require(error.called, "partial import did not report error")
            require(contents(repo) == before and not plugin.iface.messages.success, "partial import not recovered")
            observations.append(dict(case="partial_import", status="both layers recovered, no success UI"))

            # Refuse undo after a real route add. Do not conceal partial data;
            # prevent the next mutation and leave export available for recovery.
            plugin = plugin_with_history(1)
            repo = plugin.history_repository
            original_add = repo._operations._provider_add
            with patch.object(repo._operations, "_provider_add", side_effect=lambda layer, features:
                              (False, []) if layer is repo.guidance_layer else original_add(layer, features)), \
                 patch.object(repo._operations, "_provider_delete", return_value=False):
                try:
                    repo.append(**fixture(2))
                    raise AssertionError("undo failure accepted")
                except HistoryOperationError as exc:
                    require(not exc.recovered and "일부 변경" in str(exc), "undo failure hidden")
            require(repo.needs_recovery and repo.route_for_history("h2") is not None, "partial state not marked")
            try:
                repo.delete_all()
                raise AssertionError("mutation after failed recovery accepted")
            except HistoryOperationError as exc:
                require(not exc.recovered, "recovery block lost")
            require(plugin._write_gpx_history(repo.route_layer, repo.guidance_layer, output / "recovery.gpx") == (2, 1),
                    "export unavailable after failed recovery")
            observations.append(dict(case="failed_recovery", status="partial data disclosed, writes blocked, export allowed"))

            plugin = plugin_with_history(1)
            repo = plugin.history_repository
            plugin.active_route_history_id = "h1"
            original_delete = repo._operations._provider_delete

            def fail_guide_delete(layer, ids):
                return False if layer is repo.guidance_layer else original_delete(layer, ids)

            with patch.object(repo._operations, "_provider_delete", side_effect=fail_guide_delete), \
                 patch.object(repo._operations, "_provider_add", return_value=(False, [])), \
                 patch("kakao_qgis_bridge.plugin.QMessageBox.question", return_value=MSGBOX_YES), \
                 patch("kakao_qgis_bridge.plugin.QMessageBox.critical") as error:
                plugin._delete_route_history("h1")
                require(error.called and "일부 변경" in error.call_args.args[-1]
                        and "현재 남은 이력: 경로 0건, 안내 1건" in error.call_args.args[-1],
                        "failed undo not disclosed in UI")
            require(repo.needs_recovery and repo.route_for_history("h1") is None
                    and plugin.active_route_history_id is None and not plugin.iface.messages.info,
                    "failed delete recovery kept nonexistent active history or success UI")
            observations.append(dict(case="failed_delete_recovery_ui", status="actual missing route clears active state, error UI"))

            # A valid route result still releases the viewer busy state if only
            # history storage fails. It must not advertise a saved history ID.
            request = fixture(2)
            route_request = RouteRequestData(request["origin"], request["destination"], "RECOMMEND", (), (),
                                            request["vehicle_options"], "출발", "도착")
            result = RouteResultData("r2", ((127, 37.5), (127.003, 37.502)), 3500, 600, tuple(request["guides"]))
            for fail_storage in (False, True):
                plugin = KakaoQgisBridgePlugin(Iface())
                plugin._ensure_route_history_layers()
                if fail_storage:
                    plugin.guidance_history_layer = readonly_guide
                with patch("kakao_qgis_bridge.plugin.QMessageBox.critical"):
                    plugin._handle_route_result(result, route_request)
                require(plugin.route_layer is not None and plugin.route_guidance_layer is not None, "route display lost")
                if fail_storage:
                    require(plugin.active_route_history_id is None and plugin._current_guidance_payload["history_id"] == ""
                            and plugin._last_route_status[0] is False and not plugin.iface.messages.success
                            and "이력 저장에 실패" in plugin.iface.messages.warnings[-1], "route storage failure hidden")
                else:
                    require(plugin.active_route_history_id and plugin._last_route_status[0] is True
                            and plugin.history_repository.route_for_history(plugin.active_route_history_id) is not None,
                            "normal route storage regressed")
            observations.append(dict(case="route_result_ui", status="normal save succeeds, unsaved route warns and releases busy state"))
        return dict(qgis_version=Qgis.QGIS_VERSION, status="ok", observations=observations)
    finally:
        QgsProject.instance().removeAllMapLayers()
        app.exitQgis()


if __name__ == "__main__":
    print("FAILURE_AUDIT=" + json.dumps(run(Path(sys.argv[1]).resolve()), ensure_ascii=False))
