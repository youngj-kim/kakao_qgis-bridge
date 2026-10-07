"""Pure value rules for history imports; never silently repair invalid values."""
import json
import math
import re
from dataclasses import dataclass, field

from .mobility import (MAX_ROUTE_WAYPOINTS, ROUTE_PRIORITIES, ROUTE_AVOID_OPTIONS,
                      ROUTE_CAR_TYPES, ROUTE_CAR_FUELS)


class HistoryValidationError(RuntimeError):
    pass


@dataclass
class ImportReport:
    routes: int = 0
    guides: int = 0
    skipped_routes: int = 0
    skipped_guides: int = 0
    duplicates: int = 0
    warnings: list = field(default_factory=list)

    def __iter__(self):
        yield self.routes
        yield self.guides

    def warn(self, message):
        if message not in self.warnings:
            self.warnings.append(message)


def integer(value, minimum=0):
    if isinstance(value, bool) or not (isinstance(value, int) or
            isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip())):
        raise ValueError("정수 값이 필요합니다")
    result = int(value)
    if result < minimum or result > 2147483647:
        raise ValueError("정수 값이 허용 범위를 벗어났습니다")
    return result


def coordinate(value, latitude=False):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("좌표는 숫자여야 합니다")
    result = float(value)
    limit = 90 if latitude else 180
    if not math.isfinite(result) or abs(result) > limit:
        raise ValueError("좌표가 유한한 WGS84 범위를 벗어났습니다")
    return result


def normalize_values(values, kind, shapefile, report):
    """Return normalized values, retaining which source fields were provided."""
    values = dict(values)
    provided = {key for key, value in values.items() if value is not None}
    required = ("history_id", "origin_lon", "origin_lat", "destination_lon", "destination_lat") \
        if kind == "route" else ("history_id", "sequence", "longitude", "latitude")
    for key in required:
        if key not in provided:
            raise ValueError(f"{key}: 필수 값이 없습니다")
    for key, limit in (("history_id", 36), ("route_id", 64)):
        value = values.get(key)
        if value is not None and (not isinstance(value, str) or
                len(value) > limit or key == "history_id" and not value.strip()):
            raise ValueError(f"{key}: 유효한 문자열 ID가 필요합니다 (최대 {limit}자)")
    version = values.get("schema_ver")
    if version is not None:
        version = integer(version, 1)
    if version is None or version == 1:
        report.warn("레거시 스키마를 필수 데이터 검사 후 버전 2로 복원했습니다.")
    if version is not None and version not in (1, 2):
        raise ValueError("schema_ver: 지원하지 않는 스키마 버전입니다")
    values["schema_ver"] = 2
    for key in ("origin_lon", "origin_lat", "destination_lon", "destination_lat",
                "longitude", "latitude"):
        if key in values:
            values[key] = coordinate(values[key], key.endswith("lat") or key == "latitude")
    numeric = ("distance_m", "duration_s", "guidance_count", "sequence", "section_no",
               "guide_type", "cum_distance_m", "cum_duration_s", "road_index")
    for key in numeric:
        if key in values and values[key] is not None:
            try:
                minimum = 1 if key == "sequence" else -1 if key == "road_index" else 0
                values[key] = integer(values[key], minimum)
            except ValueError as exc:
                raise ValueError(f"{key}: {exc}") from exc
    defaults = dict(route_id="", searched_at="", distance_m=0, duration_s=0)
    if kind == "route":
        defaults.update(origin_name="", destination_name="", waypoints_json="[]",
                        result_summary="", priority="RECOMMEND", avoid="", car_type=1,
                        car_fuel="GASOLINE", car_hipass=0)
    else:
        defaults.update(section_no=0, guide_type=0, category="other", guidance="", name="",
                        cum_distance_m=0, cum_duration_s=0, road_index=0)
    missing = [key for key in defaults if values.get(key) is None]
    if missing:
        report.warn(f"{kind}: 누락된 선택 값을 기본값으로 복원: {', '.join(missing)}")
    for key, default in defaults.items():
        if values.get(key) is None:
            values[key] = default
        if isinstance(default, str) and not isinstance(values[key], str):
            raise ValueError(f"{key}: 문자열 값이 필요합니다")
    if kind == "route":
        if values["priority"] not in ROUTE_PRIORITIES:
            raise ValueError("priority: 지원하지 않는 경로 옵션입니다")
        if any(item not in ROUTE_AVOID_OPTIONS for item in values["avoid"].split("|") if item):
            raise ValueError("avoid: 지원하지 않는 회피 옵션입니다")
        values["car_type"] = integer(values["car_type"], 1)
        values["car_hipass"] = integer(values["car_hipass"])
        if (values["car_type"] not in ROUTE_CAR_TYPES or values["car_fuel"] not in ROUTE_CAR_FUELS
                or values["car_hipass"] not in (0, 1)):
            raise ValueError("car_type/car_fuel/car_hipass: 지원하지 않는 차량 옵션입니다")
        try:
            waypoints = json.loads(values["waypoints_json"])
        except (ValueError, TypeError) as exc:
            if not shapefile:
                raise ValueError("waypoints_json: JSON을 읽을 수 없습니다") from exc
            report.warn("SHP 경유지 JSON을 읽을 수 없어 입력 복원용 경유지를 비웠습니다.")
            waypoints = []
        if not isinstance(waypoints, list) or len(waypoints) > MAX_ROUTE_WAYPOINTS:
            raise ValueError("waypoints_json: 허용 개수 이내의 목록이 필요합니다")
        for point in waypoints:
            if not isinstance(point, dict) or "lon" not in point or "lat" not in point:
                raise ValueError("waypoints_json: 경유지 lon/lat가 필요합니다")
            point["lon"] = coordinate(point["lon"])
            point["lat"] = coordinate(point["lat"], True)
            if "label" in point and not isinstance(point["label"], str):
                raise ValueError("waypoints_json: label은 문자열이어야 합니다")
        values["waypoints_json"] = json.dumps(waypoints, ensure_ascii=False, separators=(",", ":"))
    return values, provided
