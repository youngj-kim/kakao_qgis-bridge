"""Read supported history files and restore their fields into a repository.

The repository owns stored features; this service owns source files and field
conversion. UI, active route state and viewer updates remain with the caller.
"""
from qgis.core import (NULL, QgsFeature, QgsVectorLayer, QgsGeometry,
                       QgsCoordinateReferenceSystem, QgsWkbTypes)
from qgis.PyQt.QtCore import QDate, QDateTime, Qt
from .history_validation import (ImportReport, HistoryValidationError,
                                 normalize_values, coordinate)
from .history_formats import (
    ROUTE_HISTORY_LAYER_NAME, GUIDANCE_HISTORY_LAYER_NAME,
    paired_output_paths, full_history_field_specs, history_value,
)


class HistoryImportService:
    def __init__(self, repository):
        self.repository = repository

    def import_file(self, input_path):
        routes, guides = self.open_sources(input_path)
        report = ImportReport()
        try:
            incoming_routes = self.read_rows(routes, "route", input_path.suffix.lower() == ".shp", report)
            incoming_guides = self.read_rows(guides, "guidance", input_path.suffix.lower() == ".shp", report,
                                            legacy_routes=incoming_routes)
            old_routes = self.read_rows(self.repository.route_layer, "route", False, ImportReport())
            old_guides = self.read_rows(self.repository.guidance_layer, "guidance", False, ImportReport())
            route_rows, guide_rows = self.validate_batch(
                incoming_routes, incoming_guides, old_routes, old_guides, report)
        except HistoryValidationError as exc:
            raise HistoryValidationError(f"{input_path}\n{exc}") from exc
        self.repository.ensure_layers()
        route_features = self.to_features(route_rows, self.repository.route_layer)
        guide_features = self.to_features(guide_rows, self.repository.guidance_layer)
        report.routes, report.guides = self.repository.add_history_features(route_features, guide_features)
        return report

    @staticmethod
    def to_features(rows, target):
        features = []
        for values, _provided, geometry, _context in rows:
            feature = QgsFeature(target.fields())
            feature.setGeometry(geometry)
            feature.setAttributes([values.get(name) for name in target.fields().names()])
            features.append(feature)
        return features

    @staticmethod
    def read_rows(layer, kind, shapefile, report, legacy_routes=None):
        if layer is None:
            return []
        # OGR may expose an empty GeoJSON with no fields or CRS. There are no
        # coordinates to validate or transform in this case.
        if layer.featureCount() == 0:
            return []
        if not layer.crs().isValid() or layer.crs() != QgsCoordinateReferenceSystem("EPSG:4326"):
            raise HistoryValidationError(f"{layer.name()}: CRS {layer.crs().authid() or '미상'}, EPSG:4326이 필요합니다.")
        names = set(layer.fields().names())
        legacy_guides = (shapefile and kind == "guidance" and
                         not names.intersection({"history_id", "hist_id", "schema_ver", "schema_v"}))
        legacy_route_ids = {}
        if legacy_guides:
            for route in legacy_routes or []:
                route_id = route[0].get("route_id")
                if route_id:
                    legacy_route_ids.setdefault(route_id, set()).add(route[0]["history_id"])
        rows = []
        mandatory = {"history_id", "route_id", "sequence", "guidance_count", "origin_lon",
                     "origin_lat", "destination_lon", "destination_lat", "longitude", "latitude"}
        for number, feature in enumerate(layer.getFeatures(), 1):
            context = f"{layer.name()} 행 {number} (history_id={history_value(feature, names, 'history_id', 'hist_id')})"
            try:
                values = {}
                for spec in full_history_field_specs(kind):
                    full, short = spec["source"], spec["name"]
                    value = history_value(feature, names, full, short)
                    # Earlier guidance SHP exports used OGR-truncated names
                    # rather than our current explicit short-name schema.
                    legacy_name = {"cum_distance_m": "cum_distan", "cum_duration_s": "cum_durati"}.get(full)
                    if legacy_guides and full not in names and short not in names and legacy_name in names:
                        value = feature[legacy_name]
                    values[full] = None if value is None or value == NULL else value
                    # OGR infers ISO timestamps in GeoJSON as Qt date values.
                    if full == "searched_at" and isinstance(value, (QDate, QDateTime)):
                        values[full] = value.toString(Qt.DateFormat.ISODate)
                    if full != short and full in names and short in names:
                        alternate = feature[short]
                        alternate = None if alternate is None or alternate == NULL else alternate
                        if values[full] != alternate:
                            if full in mandatory:
                                raise ValueError(f"{full}/{short}: 전체/짧은 필드 값이 충돌합니다")
                            report.warn(f"{context}: {full}/{short} 차이, 전체 이름을 유지했습니다.")
                if legacy_guides:
                    matched = legacy_route_ids.get(values.get("route_id"), set())
                    if len(matched) != 1:
                        raise ValueError("history_id: 예전 안내 SHP의 route_id를 짝 경로 이력 하나에 연결할 수 없습니다")
                    values["history_id"] = next(iter(matched))
                    report.warn("예전 안내 SHP의 history_id를 짝 경로의 유일한 route_id로 복원했습니다. 예전 누적 거리·시간 필드명도 함께 읽었습니다.")
                values, provided = normalize_values(values, kind, shapefile, report)
                geometry = QgsGeometry(feature.geometry())
                expected = QgsWkbTypes.LineString if kind == "route" else QgsWkbTypes.Point
                flat = QgsWkbTypes.flatType(geometry.wkbType())
                if (geometry.isNull() or geometry.isEmpty() or QgsWkbTypes.hasZ(geometry.wkbType())
                        or QgsWkbTypes.hasM(geometry.wkbType())):
                    raise ValueError("geometry: 비어 있지 않은 2차원 geometry가 필요합니다")
                if kind == "route" and flat == QgsWkbTypes.MultiLineString:
                    parts = geometry.asMultiPolyline()
                    if len(parts) != 1:
                        raise ValueError("geometry: 여러 부분인 경로는 지원하지 않습니다")
                    geometry = QgsGeometry.fromPolylineXY(parts[0])
                elif flat != expected:
                    raise ValueError("geometry: 경로는 선, 안내는 단일 점이어야 합니다")
                points = geometry.asPolyline() if kind == "route" else [geometry.asPoint()]
                if kind == "route" and len(points) < 2:
                    raise ValueError("geometry: 경로에 최소 두 점이 필요합니다")
                for point in points:
                    coordinate(point.x())
                    coordinate(point.y(), True)
                if kind == "guidance" and (abs(points[0].x() - values["longitude"]) > 1e-7 or
                        abs(points[0].y() - values["latitude"]) > 1e-7):
                    # Older history outputs retain full geometry precision but
                    # round double attributes to five decimal places. Accept
                    # that specific representation, not arbitrary nearby points.
                    if (abs(round(points[0].x(), 5) - values["longitude"]) <= 1e-9 and
                            abs(round(points[0].y(), 5) - values["latitude"]) <= 1e-9):
                        values["longitude"], values["latitude"] = points[0].x(), points[0].y()
                        report.warn("기존 안내 좌표의 소수점 5자리 반올림을 확인하여 geometry의 정밀 좌표로 복원했습니다. 원본 파일은 변경하지 않았습니다.")
                    else:
                        raise ValueError("longitude/latitude: 안내 geometry와 좌표가 다릅니다")
                rows.append((values, provided, geometry, context))
            except (ValueError, TypeError, OverflowError) as exc:
                raise HistoryValidationError(f"{context}: {exc}") from exc
        return rows

    @staticmethod
    def same_geometry(a, b):
        ap, bp = list(a.vertices()), list(b.vertices())
        return len(ap) == len(bp) and all(abs(x.x() - y.x()) <= 1e-7 and
                abs(x.y() - y.y()) <= 1e-7 for x, y in zip(ap, bp))

    @classmethod
    def same_row(cls, a, b, core=False):
        av, provided, ag, _ = a
        bv, other_provided, bg, _ = b
        if not cls.same_geometry(ag, bg):
            return False
        keys = ({"origin_lon", "origin_lat", "destination_lon", "destination_lat", "route_id",
                 "distance_m", "duration_s"} if core else set(av))
        for key in keys:
            if core and (key not in provided or key not in other_provided):
                continue
            x, y = av.get(key), bv.get(key)
            if key.endswith(("_lon", "_lat")) or key in ("longitude", "latitude"):
                rounded_pair = (core and x is not None and y is not None and
                                (abs(round(x, 5) - y) <= 1e-9 or abs(round(y, 5) - x) <= 1e-9))
                if x is None or y is None or abs(x - y) > 1e-7 and not rounded_pair:
                    return False
            elif x != y:
                return False
        return True

    @classmethod
    def validate_batch(cls, routes, guides, old_routes, old_guides, report):
        def indexed(rows, guidance=False, incoming=True):
            result = {}
            for row in rows:
                value = row[0]
                key = (value["history_id"], value["sequence"]) if guidance else value["history_id"]
                if key in result:
                    if not cls.same_row(row, result[key]):
                        raise HistoryValidationError(f"{row[3]}: 동일 식별자의 내용이 충돌합니다 ({key})")
                    if incoming:
                        report.duplicates += 1
                else:
                    result[key] = row
            return result
        ri, gi = indexed(routes), indexed(guides, True)
        old_ri, old_gi = indexed(old_routes, incoming=False), indexed(old_guides, True, False)

        def grouped(index):
            groups = {}
            for key, row in index.items():
                groups.setdefault(key[0], {})[key] = row
            return groups

        guides_by_history = grouped(gi)
        old_guides_by_history = grouped(old_gi)
        for (hid, _seq), guide in gi.items():
            route = ri.get(hid) or old_ri.get(hid)
            if route is None:
                raise HistoryValidationError(f"{guide[3]}: 연결할 경로가 없는 안내입니다")
            if ("route_id" in guide[1] and "route_id" in route[1] and
                    guide[0]["route_id"] != route[0]["route_id"]):
                raise HistoryValidationError(f"{guide[3]}: route_id가 연결 경로와 다릅니다")
        for hid, row in ri.items():
            count = len(guides_by_history.get(hid, {}))
            if "guidance_count" in row[1] and row[0]["guidance_count"] != count:
                raise HistoryValidationError(f"{row[3]}: guidance_count와 연결 안내 건수가 다릅니다")
            if "guidance_count" not in row[1]:
                row[0]["guidance_count"] = count
                report.warn("누락된 guidance_count를 실제 안내 건수로 복원했습니다.")
        accepted_routes, accepted_guides = [], []
        for hid, row in ri.items():
            if hid not in old_ri:
                accepted_routes.append(row)
            elif not cls.same_row(row, old_ri[hid], core=True):
                raise HistoryValidationError(f"{row[3]}: 기존 세션의 같은 ID 경로와 충돌합니다")
            else:
                report.skipped_routes += 1
                if not cls.same_row(row, old_ri[hid]):
                    report.warn(f"{hid}: 저장 형식에 따른 속성 차이가 있어 기존 세션의 값을 유지했습니다.")
        for hid in {key[0] for key in gi} | set(ri):
            current = old_guides_by_history.get(hid, {})
            incoming = guides_by_history.get(hid, {})
            if current:
                if set(current) != set(incoming) or any(not cls.same_row(row, current[key], core=True)
                        for key, row in incoming.items()):
                    raise HistoryValidationError(f"history_id={hid}: 기존 안내와 충돌하거나 일부 안내가 누락됐습니다")
                # Guide identity includes sequence, type, coordinates and distance/time;
                # optional text may have been truncated by SHP.
                for key, row in incoming.items():
                    for name in ("guide_type", "section_no", "longitude", "latitude",
                                 "cum_distance_m", "cum_duration_s", "road_index"):
                        different = (abs(row[0][name] - current[key][0][name]) > 1e-7
                                     if name in ("longitude", "latitude") else row[0][name] != current[key][0][name])
                        if name in row[1] and name in current[key][1] and different:
                            raise HistoryValidationError(f"{row[3]}: 기존 안내의 {name} 값과 충돌합니다")
                    if not cls.same_row(row, current[key]):
                        report.warn(f"{hid}: 안내 선택 속성 차이, 기존 값을 유지했습니다.")
                report.skipped_guides += len(incoming)
            else:
                if hid not in ri and old_ri[hid][0].get("guidance_count") != len(incoming):
                    raise HistoryValidationError(f"history_id={hid}: 기존 경로의 안내 건수와 다릅니다")
                accepted_guides.extend(incoming.values())
        return accepted_routes, accepted_guides

    def open_sources(self, input_path):
        suffix = input_path.suffix.lower()
        if suffix == ".gpkg":
            route_source = QgsVectorLayer(
                f"{input_path}|layername={ROUTE_HISTORY_LAYER_NAME}",
                ROUTE_HISTORY_LAYER_NAME,
                "ogr",
            )
            guidance_source = QgsVectorLayer(
                f"{input_path}|layername={GUIDANCE_HISTORY_LAYER_NAME}",
                GUIDANCE_HISTORY_LAYER_NAME,
                "ogr",
            )
        elif suffix == ".geojson":
            route_path, guidance_path = paired_output_paths(input_path, ".geojson")
            route_source = QgsVectorLayer(
                str(route_path),
                "Kakao Route History",
                "ogr",
            )
            guidance_source = QgsVectorLayer(
                str(guidance_path),
                "Kakao Guidance History",
                "ogr",
            )
        elif suffix == ".shp":
            route_path, guidance_path = paired_output_paths(
                input_path,
                ".shp",
            )
            route_source = QgsVectorLayer(
                str(route_path),
                "Kakao Route History",
                "ogr",
            )
            guidance_source = QgsVectorLayer(
                str(guidance_path),
                "Kakao Guidance History",
                "ogr",
            )
        else:
            raise RuntimeError("지원하지 않는 이력 파일 형식입니다.")

        if not route_source.isValid():
            raise RuntimeError("경로 이력 레이어를 열지 못했습니다.")
        if not guidance_source.isValid():
            raise RuntimeError("안내 이력 레이어를 열지 못했습니다.")

        return route_source, guidance_source
