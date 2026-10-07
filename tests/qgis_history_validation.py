"""Real file import validation; rejected batches must preserve data and selection."""
import copy
import json
import sys
import tempfile
from pathlib import Path


def run(root):
    sys.path.insert(0, str(root))
    from qgis.core import (Qgis, QgsApplication, QgsLineSymbol, QgsMarkerSymbol,
                           QgsSingleSymbolRenderer, QgsVectorLayer)
    from kakao_qgis_bridge.history_repository import HistoryRepository
    from kakao_qgis_bridge.history_import_service import HistoryImportService
    from kakao_qgis_bridge.history_validation import HistoryValidationError, ImportReport
    app = QgsApplication([], False)
    app.initQgis()
    checks = []

    def repository():
        return HistoryRepository(lambda: QgsLineSymbol.createSimple({}),
                                 lambda: QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple({})))

    route = dict(schema_ver=2, history_id="h1", route_id="r1", origin_lon=127, origin_lat=37,
                 destination_lon=127.1, destination_lat=37.1, distance_m=100, duration_s=10,
                 guidance_count=1)
    guide = dict(schema_ver=2, history_id="h1", route_id="r1", sequence=1,
                 longitude=127.01, latitude=37.01, distance_m=20, duration_s=2)
    def feature(values, geometry):
        return dict(type="Feature", properties=values, geometry=geometry)
    rf = feature(route, dict(type="LineString", coordinates=[[127, 37], [127.1, 37.1]]))
    gf = feature(guide, dict(type="Point", coordinates=[127.01, 37.01]))

    def write(directory, routes, guides):
        path = directory / "input_routes.geojson"
        for name, rows in (("routes", routes), ("guidance", guides)):
            (directory / f"input_{name}.geojson").write_text(
                json.dumps(dict(type="FeatureCollection", features=rows)), encoding="utf-8")
        return path

    def snapshot(repo):
        return [(None if layer is None else
                 ([ (bytes(f.geometry().asWkb()), [str(v) for v in f.attributes()])
                    for f in layer.getFeatures()], sorted(layer.selectedFeatureIds())))
                for layer in (repo.route_layer, repo.guidance_layer)]

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
        directory = Path(temporary)
        repo = repository()
        service = HistoryImportService(repo)
        report = service.import_file(write(directory, [rf], [gf]))
        assert tuple(report) == (1, 1) and report.warnings
        repo.route_layer.selectAll()
        repo.guidance_layer.selectAll()
        before = snapshot(repo)
        repeated = service.import_file(write(directory, [rf], [gf]))
        assert tuple(repeated) == (0, 0) and repeated.skipped_routes == 1
        assert snapshot(repo) == before
        duplicated = service.import_file(write(directory, [rf, rf], [gf, gf]))
        assert duplicated.duplicates == 2 and snapshot(repo) == before
        checks.append("normal file, existing IDs, exact batch duplicates, selection preservation")

        def reject(label, routes, guides):
            try:
                service.import_file(write(directory, routes, guides))
            except HistoryValidationError as exc:
                assert str(directory) in str(exc), str(exc)
            else:
                raise AssertionError(label + " accepted")
            assert snapshot(repo) == before, label + " mutated repository"
            checks.append(label)

        for key, value in (("schema_ver", 3), ("history_id", " "), ("origin_lon", 181),
                           ("origin_lat", None), ("distance_m", "1.5"), ("guidance_count", 2),
                           ("waypoints_json", "{"), ("priority", "unknown")):
            bad = copy.deepcopy(rf)
            bad["properties"][key] = value
            reject("invalid route " + key, [bad], [gf])
        for key, value in (("sequence", 0), ("longitude", 128), ("history_id", "orphan"),
                           ("route_id", "different")):
            bad = copy.deepcopy(gf)
            bad["properties"][key] = value
            reject("invalid guide " + key, [rf], [bad])
        for geometry in (dict(type="Point", coordinates=[127, 37]),
                         dict(type="LineString", coordinates=[[127, 37, 10], [127.1, 37.1, 10]]),
                         dict(type="MultiLineString", coordinates=[[[127, 37], [127.1, 37.1]],
                                                                   [[128, 38], [128.1, 38.1]]])):
            bad = copy.deepcopy(rf)
            bad["geometry"] = geometry
            reject("invalid geometry " + geometry["type"], [bad], [gf])
        conflict = copy.deepcopy(rf)
        conflict["properties"]["distance_m"] = 101
        reject("conflicting batch route", [rf, conflict], [gf])
        reject("conflicting existing route", [conflict], [gf])
        conflict = copy.deepcopy(gf)
        conflict["properties"]["distance_m"] = 21
        reject("conflicting batch guide", [rf], [gf, conflict])
        reject("conflicting existing guide", [rf], [conflict])
        bad = copy.deepcopy(rf)
        bad["properties"]["hist_id"] = "different"
        reject("full/short required field conflict", [bad], [gf])
        # No guide properties/fields is valid for an empty guide layer.
        empty = copy.deepcopy(rf)
        empty["properties"].update(history_id="empty", route_id="", guidance_count=0)
        fresh = repository()
        assert tuple(HistoryImportService(fresh).import_file(write(directory, [empty], []))) == (1, 0)
        checks.append("empty guidance file without fields")
        # Legacy NULL/missing optional data, single-part multi-line normalization.
        legacy = copy.deepcopy(empty)
        legacy["properties"].pop("schema_ver")
        legacy["properties"].pop("guidance_count")
        legacy["properties"]["car_type"] = None
        legacy["geometry"] = dict(type="MultiLineString", coordinates=[rf["geometry"]["coordinates"]])
        fresh = repository()
        report = HistoryImportService(fresh).import_file(write(directory, [legacy], []))
        assert report.routes == 1 and report.warnings
        assert fresh.route_for_history("empty")["car_type"] == 1
        checks.append("legacy missing/NULL fields and single-part MultiLineString")
        precise = copy.deepcopy(gf)
        precise["geometry"]["coordinates"] = [127.0100049, 37.0099951]
        precise["properties"]["road_index"] = -1
        rounded = repository()
        report = HistoryImportService(rounded).import_file(write(directory, [rf], [precise]))
        assert tuple(report) == (1, 1) and any("5자리" in warning for warning in report.warnings)
        restored = rounded.guidance_for_history("h1")[0]
        assert abs(restored["longitude"] - 127.0100049) < 1e-10
        assert restored["road_index"] == -1
        assert tuple(HistoryImportService(rounded).import_file(write(directory, [rf], [precise]))) == (0, 0)
        unrounded = copy.deepcopy(precise)
        unrounded["properties"]["longitude"] = 127.010001
        reject("nearby coordinates without five-decimal rounding pattern", [rf], [unrounded])
        checks.append("legacy five-decimal rounding restores precise geometry and deduplicates")
        # A session may contain unrounded request endpoints while an older
        # saved file has five-place attributes; geometry/route identity agrees.
        precise_route = copy.deepcopy(rf)
        precise_route["properties"]["origin_lon"] = 127.0000049
        mixed = repository()
        mixed_service = HistoryImportService(mixed)
        mixed_service.import_file(write(directory, [precise_route], [gf]))
        assert tuple(mixed_service.import_file(write(directory, [rf], [gf]))) == (0, 0)
        assert abs(mixed.route_for_history("h1")["origin_lon"] - 127.0000049) < 1e-10
        not_rounded = copy.deepcopy(rf)
        not_rounded["properties"]["origin_lon"] = 127.000001
        try:
            mixed_service.import_file(write(directory, [not_rounded], [gf]))
        except HistoryValidationError:
            pass
        else:
            raise AssertionError("arbitrary request endpoint change accepted")
        checks.append("rounded legacy request endpoints match precise session without overwrite")
        # Matching routes with no stored guides can be replenished.
        fresh = repository()
        importer = HistoryImportService(fresh)
        importer.import_file(write(directory, [rf], [gf]))
        fresh.guidance_layer.dataProvider().deleteFeatures([f.id() for f in fresh.guidance_layer.getFeatures()])
        assert tuple(importer.import_file(write(directory, [rf], [gf]))) == (0, 1)
        checks.append("replenish absent guides for matching route")
        # Existing partial sets are refused, rather than silently filled.
        extended_route, second = copy.deepcopy(rf), copy.deepcopy(gf)
        extended_route["properties"]["guidance_count"] = 2
        second["properties"]["sequence"] = 2
        saved = snapshot(fresh)
        try:
            importer.import_file(write(directory, [extended_route], [gf, second]))
        except HistoryValidationError:
            pass
        else:
            raise AssertionError("partial guide set repaired without consent")
        assert snapshot(fresh) == saved
        checks.append("existing partial guidance set refused without mutation")
        # Exercise the actual DBF 254-character truncation of waypoint JSON.
        from qgis.core import QgsProject
        from kakao_qgis_bridge.history_export_service import HistoryExportService
        from kakao_qgis_bridge.history_formats import full_history_field_specs
        long_json = json.dumps([dict(lon=127.01, lat=37.01, label="경유지" * 150)], ensure_ascii=False)
        feature_id = next(fresh.route_layer.getFeatures()).id()
        fresh.route_layer.dataProvider().changeAttributeValues({feature_id: {
            fresh.route_layer.fields().indexOf("waypoints_json"): long_json}})
        exporter = HistoryExportService(QgsProject.instance().transformContext())
        for kind, layer, geometry in (("route", fresh.route_layer, "LineString"),
                                      ("guidance", fresh.guidance_layer, "Point")):
            target = directory / ("loss_" + ("routes" if kind == "route" else "guidance") + ".shp")
            specs = exporter._route_shapefile_fields() if kind == "route" else exporter._guidance_shapefile_fields()
            exporter.write_shapefile_layer(layer, target, geometry, "history", specs)
        lossy = repository()
        report = HistoryImportService(lossy).import_file(directory / "loss_routes.shp")
        assert report.routes == 1 and any("SHP" in warning for warning in report.warnings)
        assert lossy.route_for_history("h1")["waypoints_json"] == "[]"
        report = importer.import_file(directory / "loss_routes.shp")
        assert report.skipped_routes == 1 and fresh.route_for_history("h1")["waypoints_json"] == long_json
        checks.append("real SHP truncated JSON warning and existing full JSON preservation")
        # Legacy guidance SHP lacks history_id/schema and has truncated full
        # cumulative field names. Only a unique paired route_id permits recovery.
        from qgis.core import QgsVectorFileWriter
        from kakao_qgis_bridge.compat import WRITE_OVERWRITE_FILE
        legacy_guide = copy.deepcopy(gf)
        for key in ("history_id", "schema_ver"):
            legacy_guide["properties"].pop(key)
        legacy_guide["properties"].update(cum_distance_m=345, cum_duration_s=67, road_index=-1)
        legacy_source_path = directory / "legacy_source.geojson"
        legacy_source_path.write_text(json.dumps(dict(type="FeatureCollection", features=[legacy_guide])), encoding="utf-8")
        legacy_layer = QgsVectorLayer(str(legacy_source_path), "legacy", "ogr")
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName, options.fileEncoding = "ESRI Shapefile", "UTF-8"
        options.actionOnExistingFile = WRITE_OVERWRITE_FILE
        legacy_path = directory / "legacy_guidance.shp"
        written = QgsVectorFileWriter.writeAsVectorFormatV3(legacy_layer, str(legacy_path),
                                                           QgsProject.instance().transformContext(), options)
        assert int(written[0]) == 0, written
        source_repo = repository()
        HistoryImportService(source_repo).import_file(write(directory, [rf], [gf]))
        exporter.write_shapefile_layer(source_repo.route_layer, directory / "legacy_routes.shp",
                                      "LineString", "history", exporter._route_shapefile_fields())
        for extension in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            source = legacy_path.with_suffix(extension)
            if source.exists():
                (directory / ("ambiguous_guidance" + extension)).write_bytes(source.read_bytes())
        restored_repo = repository()
        report = HistoryImportService(restored_repo).import_file(directory / "legacy_routes.shp")
        assert tuple(report) == (1, 1) and any("유일한 route_id" in warning for warning in report.warnings)
        restored = restored_repo.guidance_for_history("h1")[0]
        assert restored["cum_distance_m"] == 345 and restored["cum_duration_s"] == 67 and restored["road_index"] == -1
        duplicate_route = copy.deepcopy(rf)
        duplicate_route["properties"]["history_id"] = "h2"
        source_repo = repository()
        other_guide = copy.deepcopy(gf)
        other_guide["properties"]["history_id"] = "h2"
        HistoryImportService(source_repo).import_file(write(directory, [rf, duplicate_route], [gf, other_guide]))
        exporter.write_shapefile_layer(source_repo.route_layer, directory / "ambiguous_routes.shp",
                                      "LineString", "history", exporter._route_shapefile_fields())
        empty_repo = repository()
        try:
            HistoryImportService(empty_repo).import_file(directory / "ambiguous_routes.shp")
        except HistoryValidationError:
            pass
        else:
            raise AssertionError("ambiguous legacy route_id accepted")
        assert empty_repo.route_layer is None and empty_repo.guidance_layer is None
        checks.append("legacy SHP ID/field restoration; ambiguous paired route IDs refused")
        for crs_name in ("EPSG:3857", ""):
            layer = QgsVectorLayer("LineString" + ("?crs=" + crs_name if crs_name else ""), "bad CRS", "memory")
            if not crs_name:
                from qgis.core import QgsCoordinateReferenceSystem
                layer.setCrs(QgsCoordinateReferenceSystem())
            from qgis.core import QgsFeature, QgsGeometry
            invalid = QgsFeature()
            invalid.setGeometry(QgsGeometry.fromWkt("LINESTRING (127 37, 128 38)"))
            layer.dataProvider().addFeatures([invalid])
            try:
                HistoryImportService.read_rows(layer, "route", False, ImportReport())
            except HistoryValidationError:
                pass
            else:
                raise AssertionError("bad CRS accepted")
        checks.append("non-WGS84 and unknown CRS")
    return dict(status="ok", qgis=Qgis.QGIS_VERSION, checks=checks)


if __name__ == "__main__":
    print("VALIDATION_RESULT=" + json.dumps(run(Path(sys.argv[1]).resolve()), ensure_ascii=False))
