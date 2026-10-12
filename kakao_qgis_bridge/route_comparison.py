"""Read provider history packages without importing them into Kakao history."""
import json
import math
from pathlib import Path

from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsFeature, QgsFeatureRequest,
                       QgsGeometry, QgsProviderRegistry, QgsVectorLayer, QgsWkbTypes)


SUMMARY_FIELDS = {"origin_lon", "origin_lat", "destination_lon", "destination_lat",
                  "origin_name", "destination_name", "searched_at", "history_id",
                  "distance_m", "duration_s", "waypoints_json"}


def _file_revision(path):
    # Include SQLite's WAL when present; do not hash a potentially huge package.
    revisions = []
    for candidate in (path, Path(str(path) + "-wal")):
        try:
            stat = candidate.stat()
            revisions.append((stat.st_size, stat.st_mtime_ns))
        except FileNotFoundError:
            revisions.append(None)
    return tuple(revisions)


def read_routes(filename):
    """Read only comparison metadata; fetch the selected feature's geometry later."""
    path = Path(filename).resolve()
    if path.suffix.lower() != ".gpkg":
        raise ValueError("비교는 GeoPackage (.gpkg) 파일을 지원합니다.")
    revision = _file_revision(path)
    tables = {details.name() for details in
              QgsProviderRegistry.instance().querySublayers(str(path))}
    rows = []
    for provider, table in (("카카오", "kakao_route_history"),
                            ("네이버", "naver_route_history")):
        if table not in tables:
            continue
        layer = QgsVectorLayer(f"{path}|layername={table}", table, "ogr")
        if not layer.isValid():
            raise ValueError(f"{table}: 경로 레이어를 열 수 없습니다.")
        if layer.crs() != QgsCoordinateReferenceSystem("EPSG:4326"):
            raise ValueError(f"{table}: EPSG:4326 좌표계가 필요합니다.")
        if QgsWkbTypes.flatType(layer.wkbType()) not in (QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString):
            raise ValueError(f"{table}: 경로 선 레이어가 필요합니다.")
        required = {"origin_lon", "origin_lat", "destination_lon", "destination_lat"}
        fields = set(layer.fields().names())
        if required - fields:
            raise ValueError(f"{table}: 출발·도착 좌표 필드가 없습니다.")
        selected_fields = sorted(fields & SUMMARY_FIELDS)
        no_geometry = getattr(QgsFeatureRequest, "NoGeometry", None)
        if no_geometry is None:
            no_geometry = Qgis.FeatureRequestFlag.NoGeometry
        request = QgsFeatureRequest().setFlags(no_geometry)
        request.setSubsetOfAttributes(selected_fields, layer.fields())
        for feature in layer.getFeatures(request):
            values = {}
            for name in selected_fields:
                value = feature[name]
                values[name] = value if isinstance(value, (str, int, float)) else None
            for name in required:
                value = values[name]
                limit = 90 if name.endswith("lat") else 180
                if not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > limit:
                    raise ValueError(f"{table} 행 {feature.id()}: {name} 좌표가 잘못되었습니다.")
            for name in ("distance_m", "duration_s"):
                value = values.get(name)
                if value is not None and (not isinstance(value, (int, float)) or
                                          not math.isfinite(value) or value < 0):
                    raise ValueError(f"{table} 행 {feature.id()}: {name} 값이 잘못되었습니다.")
            rows.append(dict(provider=provider, values=values, table=table,
                             file=str(path), feature_id=feature.id(), revision=revision))
    if _file_revision(path) != revision:
        raise ValueError("비교 파일이 읽는 동안 변경되었습니다. 파일을 다시 여세요.")
    if not rows:
        raise ValueError("카카오 또는 네이버 경로 이력이 있는 GPKG가 필요합니다.")
    return rows


def route_geometry(row):
    """Load and validate just one selected geometry from the indexed package."""
    path = Path(row["file"])
    if _file_revision(path) != row["revision"]:
        raise ValueError("비교 파일이 변경되었습니다. 파일을 다시 여세요.")
    layer = QgsVectorLayer(f"{path}|layername={row['table']}", row['table'], "ogr")
    if not layer.isValid() or layer.crs() != QgsCoordinateReferenceSystem("EPSG:4326"):
        raise ValueError("선택한 비교 경로 레이어를 읽을 수 없습니다.")
    request = QgsFeatureRequest().setFilterFid(row["feature_id"])
    request.setSubsetOfAttributes([])
    feature = next(layer.getFeatures(request), None)
    geometry = QgsGeometry(feature.geometry()) if feature is not None else QgsGeometry()
    if (geometry.isEmpty() or geometry.isNull() or
            QgsWkbTypes.flatType(geometry.wkbType()) not in
            (QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString)):
        raise ValueError("선택한 행에 유효한 경로 선이 없습니다.")
    if _file_revision(path) != row["revision"]:
        raise ValueError("비교 파일이 읽는 동안 변경되었습니다. 파일을 다시 여세요.")
    return geometry


def coordinate_distance(a, b):
    """Great-circle distance in metres, including at the antimeridian."""
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2 +
         math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1, h)))


def _waypoint_coordinates(values):
    waypoints = json.loads(values.get("waypoints_json") or "null")
    if not isinstance(waypoints, list):
        raise ValueError("경유지 목록이 아닙니다.")
    coordinates = []
    for item in waypoints:
        if not isinstance(item, dict):
            raise ValueError("경유지 좌표가 없습니다.")
        lon, lat = item.get("lon"), item.get("lat")
        if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in (lon, lat)) or not -180 <= lon <= 180 or not -90 <= lat <= 90):
            raise ValueError("경유지 좌표가 잘못되었습니다.")
        coordinates.append((lon, lat))
    return coordinates


def condition_message(a, b):
    av, bv = a["values"], b["values"]
    offsets = [coordinate_distance((av[f"{role}_lon"], av[f"{role}_lat"]),
                                   (bv[f"{role}_lon"], bv[f"{role}_lat"]))
               for role in ("origin", "destination")]
    messages = [f"출발점 차이 {offsets[0]:.1f}m / 도착점 차이 {offsets[1]:.1f}m"]
    if max(offsets) > 20:
        messages.append("출발·도착지가 다릅니다.")
    else:
        messages.append("출발·도착지가 20m 이내로 일치합니다.")
    try:
        first, second = [_waypoint_coordinates(v) for v in (av, bv)]
        if len(first) != len(second):
            messages.append("경유지가 다릅니다. (개수 불일치)")
        elif any(coordinate_distance(x, y) > 20 for x, y in zip(first, second)):
            messages.append("경유지가 다릅니다. (방문 순서별 좌표 차이 20m 초과)")
        elif first:
            messages.append("경유지가 방문 순서별로 20m 이내로 일치합니다.")
        else:
            messages.append("두 경로 모두 경유지가 없습니다.")
    except (ValueError, TypeError):
        messages.append("경유지 정보를 확인할 수 없습니다.")
    if a["file"] == b["file"] and a["provider"] == b["provider"] and a["feature_id"] == b["feature_id"]:
        messages.append("동일한 경로를 선택했습니다.")
    messages.append("소요 시간은 각 서비스의 조회 시점별 예측값입니다.")
    return "\n".join(messages)


def display_layer(row, label, color, *, line_style):
    from qgis.core import QgsLineSymbol
    if line_style not in {"solid", "dash"}:
        raise ValueError("비교 선 스타일은 solid 또는 dash여야 합니다.")
    layer = QgsVectorLayer("MultiLineString?crs=EPSG:4326", label, "memory")
    layer.setCustomProperty("skipMemoryLayersCheck", 1)
    geometry = route_geometry(row)
    geometry.convertToMultiType()
    feature = QgsFeature(layer.fields())
    feature.setGeometry(geometry)
    ok, _ = layer.dataProvider().addFeatures([feature])
    if not ok:
        raise ValueError("비교 경로를 지도에 표시할 수 없습니다.")
    layer.updateExtents()
    layer.renderer().setSymbol(QgsLineSymbol.createSimple(
        {"line_color": color, "line_width": "1.2",
         "line_style": line_style}))
    return layer
