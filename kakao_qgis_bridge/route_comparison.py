"""Read provider history packages without importing them into Kakao history."""
import json
import math
from pathlib import Path

from qgis.core import (QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsProviderRegistry,
                       QgsVectorLayer, QgsWkbTypes)


def read_routes(filename):
    path = Path(filename).resolve()
    if path.suffix.lower() != ".gpkg":
        raise ValueError("비교는 GeoPackage (.gpkg) 파일을 지원합니다.")
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
        required = {"origin_lon", "origin_lat", "destination_lon", "destination_lat"}
        fields = set(layer.fields().names())
        if required - fields:
            raise ValueError(f"{table}: 출발·도착 좌표 필드가 없습니다.")
        for feature in layer.getFeatures():
            geometry = QgsGeometry(feature.geometry())
            if (geometry.isEmpty() or geometry.isNull() or
                    QgsWkbTypes.flatType(geometry.wkbType()) not in
                    (QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString)):
                raise ValueError(f"{table} 행 {feature.id()}: 유효한 경로 선이 필요합니다.")
            values = {}
            for name in fields - {"fid", "geom"}:
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
            rows.append(dict(provider=provider, values=values, geometry=geometry,
                             file=str(path), feature_id=feature.id()))
    if not rows:
        raise ValueError("카카오 또는 네이버 경로 이력이 있는 GPKG가 필요합니다.")
    return rows


def coordinate_distance(a, b):
    """Great-circle distance in metres, including at the antimeridian."""
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2 +
         math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1, h)))


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
        waypoints = [json.loads(v.get("waypoints_json") or "null") for v in (av, bv)]
        if not all(isinstance(w, list) for w in waypoints):
            raise ValueError()
        if waypoints[0] != waypoints[1]:
            messages.append("경유지가 다릅니다.")
    except (ValueError, TypeError):
        messages.append("경유지 정보를 확인할 수 없습니다.")
    if a["file"] == b["file"] and a["provider"] == b["provider"] and a["feature_id"] == b["feature_id"]:
        messages.append("동일한 경로를 선택했습니다.")
    messages.append("소요 시간은 각 서비스의 조회 시점별 예측값입니다.")
    return "\n".join(messages)


def display_layer(row, label, color):
    from qgis.core import QgsLineSymbol
    layer = QgsVectorLayer("MultiLineString?crs=EPSG:4326", label, "memory")
    geometry = QgsGeometry(row["geometry"])
    geometry.convertToMultiType()
    feature = QgsFeature(layer.fields())
    feature.setGeometry(geometry)
    ok, _ = layer.dataProvider().addFeatures([feature])
    if not ok:
        raise ValueError("비교 경로를 지도에 표시할 수 없습니다.")
    layer.updateExtents()
    layer.renderer().setSymbol(QgsLineSymbol.createSimple(
        {"line_color": color, "line_width": "1.2",
         "line_style": "solid" if label.startswith("A") else "dash"}))
    return layer
