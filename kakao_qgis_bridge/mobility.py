"""Pure Kakao Mobility request validation and response parsing."""

import json
import math
from dataclasses import dataclass
from uuid import uuid4


ROUTE_ENDPOINT = "https://apis-navi.kakaomobility.com/v1/directions"
ROUTE_PRIORITIES = {
    "RECOMMEND": "추천",
    "TIME": "최단 시간",
    "DISTANCE": "최단 거리",
}
ROUTE_AVOID_OPTIONS = {
    "toll": "유료도로",
    "motorway": "자동차전용도로",
    "ferries": "페리",
    "schoolzone": "어린이보호구역",
    "uturn": "유턴",
}
ROUTE_CAR_TYPES = {
    1: "소형",
    2: "중형",
    3: "대형",
    4: "대형 화물",
    5: "특수 화물",
    6: "경차",
    7: "이륜차",
}
ROUTE_CAR_FUELS = {
    "GASOLINE": "휘발유",
    "DIESEL": "경유",
    "LPG": "LPG",
}
MAX_ROUTE_WAYPOINTS = 5


class RouteValidationError(ValueError):
    pass


class MobilityResponseError(ValueError):
    pass


@dataclass(frozen=True)
class RouteRequestData:
    origin: tuple
    destination: tuple
    priority: str
    waypoints: tuple
    avoid_options: tuple
    vehicle_options: dict
    origin_label: str
    destination_label: str


@dataclass(frozen=True)
class RouteResultData:
    route_id: str
    points: tuple
    distance: int
    duration: int
    guides: tuple


def _coordinate(lon, lat, label):
    try:
        lon = float(lon)
        lat = float(lat)
    except (TypeError, ValueError) as exc:
        raise RouteValidationError(f"{label} 좌표가 올바르지 않습니다.") from exc
    if not math.isfinite(lon) or not math.isfinite(lat):
        raise RouteValidationError(f"{label} 좌표가 올바르지 않습니다.")
    if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
        raise RouteValidationError(f"{label} 좌표가 범위를 벗어났습니다.")
    return lon, lat


def _json_value(raw, default, error_message):
    try:
        return json.loads(raw) if raw else default
    except json.JSONDecodeError as exc:
        raise RouteValidationError(error_message) from exc


def normalize_route_request(
    origin_lon,
    origin_lat,
    destination_lon,
    destination_lat,
    priority,
    waypoints_json,
    avoid_json,
    vehicle_json,
    origin_label,
    destination_label,
):
    origin = _coordinate(origin_lon, origin_lat, "출발지")
    destination = _coordinate(destination_lon, destination_lat, "도착지")
    priority = priority if priority in ROUTE_PRIORITIES else "RECOMMEND"

    waypoint_data = _json_value(
        waypoints_json,
        [],
        "경유지 정보를 해석하지 못했습니다.",
    )
    if not isinstance(waypoint_data, list):
        raise RouteValidationError("경유지 정보 형식이 올바르지 않습니다.")
    if len(waypoint_data) > MAX_ROUTE_WAYPOINTS:
        raise RouteValidationError(
            f"경유지는 최대 {MAX_ROUTE_WAYPOINTS}개까지 사용할 수 있습니다."
        )

    waypoints = []
    for index, item in enumerate(waypoint_data):
        if not isinstance(item, dict):
            raise RouteValidationError("경유지 정보 형식이 올바르지 않습니다.")
        try:
            lon, lat = _coordinate(item["lon"], item["lat"], "경유지")
        except KeyError as exc:
            raise RouteValidationError("경유지 좌표가 올바르지 않습니다.") from exc
        point_id = str(item.get("id") or f"waypoint:{index + 1}")
        if not point_id.startswith("waypoint:"):
            point_id = f"waypoint:{index + 1}"
        waypoints.append(
            {
                "id": point_id,
                "label": str(item.get("label") or "").strip()[:255],
                "lon": lon,
                "lat": lat,
            }
        )

    avoid_data = _json_value(
        avoid_json,
        [],
        "경로 회피 옵션을 해석하지 못했습니다.",
    )
    if not isinstance(avoid_data, list):
        raise RouteValidationError("경로 회피 옵션 형식이 올바르지 않습니다.")
    avoid_options = tuple(
        value
        for index, value in enumerate(avoid_data)
        if value in ROUTE_AVOID_OPTIONS and value not in avoid_data[:index]
    )

    vehicle_data = _json_value(
        vehicle_json,
        {},
        "차량 설정을 해석하지 못했습니다.",
    )
    if not isinstance(vehicle_data, dict):
        raise RouteValidationError("차량 설정 형식이 올바르지 않습니다.")
    try:
        car_type = int(vehicle_data.get("car_type", 1))
    except (TypeError, ValueError):
        car_type = 1
    if car_type not in ROUTE_CAR_TYPES:
        car_type = 1
    car_fuel = str(vehicle_data.get("car_fuel", "GASOLINE"))
    if car_fuel not in ROUTE_CAR_FUELS:
        car_fuel = "GASOLINE"
    vehicle_options = {
        "car_type": car_type,
        "car_fuel": car_fuel,
        "car_hipass": vehicle_data.get("car_hipass") is True,
    }

    return RouteRequestData(
        origin=origin,
        destination=destination,
        priority=priority,
        waypoints=tuple(waypoints),
        avoid_options=avoid_options,
        vehicle_options=vehicle_options,
        origin_label=str(origin_label).strip()[:255],
        destination_label=str(destination_label).strip()[:255],
    )


def route_query_items(request):
    items = [
        ("origin", f"{request.origin[0]:.8f},{request.origin[1]:.8f}"),
        (
            "destination",
            f"{request.destination[0]:.8f},{request.destination[1]:.8f}",
        ),
    ]
    if request.waypoints:
        items.append(
            (
                "waypoints",
                "|".join(
                    f'{waypoint["lon"]:.8f},{waypoint["lat"]:.8f}'
                    for waypoint in request.waypoints
                ),
            )
        )
    if request.avoid_options:
        items.append(("avoid", "|".join(request.avoid_options)))
    items.extend(
        [
            ("priority", request.priority),
            ("car_type", str(request.vehicle_options["car_type"])),
            ("car_fuel", request.vehicle_options["car_fuel"]),
            (
                "car_hipass",
                "true" if request.vehicle_options["car_hipass"] else "false",
            ),
            ("summary", "false"),
            ("alternatives", "false"),
            ("road_details", "false"),
        ]
    )
    return items


def guidance_category(guide_type, guidance):
    if guide_type == 100:
        return "start"
    if guide_type == 101:
        return "destination"
    if guide_type == 1000:
        return "waypoint"
    if guide_type == 3 or "유턴" in guidance:
        return "uturn"
    if 30 <= guide_type <= 41 or 70 <= guide_type <= 81:
        return "roundabout"
    if guide_type in {
        1, 5, 8, 11, 24, 25, 26, 27, 28, 43, 46, 48, 76, 77, 78, 79, 80, 82,
    } or "좌회전" in guidance or "왼쪽" in guidance:
        return "left"
    if guide_type in {
        2, 6, 9, 12, 18, 19, 20, 21, 22, 44, 47, 49, 70, 71, 72, 73, 74, 83,
    } or "우회전" in guidance or "오른쪽" in guidance:
        return "right"
    if guide_type in {0, 29} or "직진" in guidance:
        return "straight"
    if guide_type in {
        7, 8, 9, 10, 11, 12, 14, 15, 16, 17, 42, 43, 44, 45, 46, 47, 48, 49,
        61, 62, 84, 85, 86, 300, 301,
    }:
        return "transition"
    return "other"


def _extract_guides(route, route_id):
    guides = []
    cumulative_distance = 0
    cumulative_duration = 0
    for section_index, section in enumerate(route.get("sections") or []):
        for guide in section.get("guides") or []:
            try:
                lon, lat = _coordinate(guide["x"], guide["y"], "안내 지점")
                guide_type = int(guide.get("type") or 0)
                distance = max(0, int(guide.get("distance") or 0))
                duration = max(0, int(guide.get("duration") or 0))
                road_index = int(guide.get("road_index") or 0)
            except (KeyError, TypeError, ValueError, RouteValidationError):
                continue
            cumulative_distance += distance
            cumulative_duration += duration
            guidance = str(guide.get("guidance") or "").strip()
            name = str(guide.get("name") or "").strip()
            guides.append(
                {
                    "route_id": route_id,
                    "sequence": len(guides) + 1,
                    "section_no": section_index + 1,
                    "guide_type": guide_type,
                    "category": guidance_category(guide_type, guidance),
                    "guidance": guidance or name or "경로 안내",
                    "name": name,
                    "distance_m": distance,
                    "duration_s": duration,
                    "cumulative_distance_m": cumulative_distance,
                    "cumulative_duration_s": cumulative_duration,
                    "road_index": road_index,
                    "longitude": lon,
                    "latitude": lat,
                }
            )
    return tuple(guides)


def parse_route_payload(payload):
    routes = payload.get("routes") or []
    if not routes:
        raise MobilityResponseError("경로 탐색 결과가 없습니다.")
    route = routes[0]
    if route.get("result_code") != 0:
        raise MobilityResponseError(
            route.get("result_msg") or "경로를 찾지 못했습니다."
        )
    points = []
    for section in route.get("sections") or []:
        for road in section.get("roads") or []:
            vertexes = road.get("vertexes") or []
            for index in range(0, len(vertexes) - 1, 2):
                try:
                    point = _coordinate(
                        vertexes[index],
                        vertexes[index + 1],
                        "경로 선형",
                    )
                except RouteValidationError:
                    continue
                if not points or point != points[-1]:
                    points.append(point)
    if len(points) < 2:
        raise MobilityResponseError("경로 선형 좌표를 찾지 못했습니다.")
    summary = route.get("summary") or {}
    route_id = str(payload.get("trans_id") or uuid4())
    return RouteResultData(
        route_id=route_id,
        points=tuple(points),
        distance=int(summary.get("distance") or 0),
        duration=int(summary.get("duration") or 0),
        guides=_extract_guides(route, route_id),
    )


def route_result_summary(distance, duration, car_type, guidance_count):
    duration_minutes = max(1, round(duration / 60))
    distance_km = distance / 1000
    car_label = ROUTE_CAR_TYPES.get(car_type, str(car_type))
    return (
        f"{duration_minutes}분 · {distance_km:.1f} km · "
        f"{car_label} · 안내 {guidance_count}개"
    )
