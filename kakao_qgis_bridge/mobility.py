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


def validate_rest_api_key(value):
    """Normalize outer whitespace; reject unsafe or mistyped header values."""
    if not isinstance(value, str):
        raise RouteValidationError("REST API 키 형식이 올바르지 않습니다.")
    value = value.strip()
    if not value or any(ord(char) < 33 or ord(char) > 126 for char in value):
        raise RouteValidationError(
            "REST API 키 형식이 올바르지 않습니다. 공백·개행·비ASCII 문자 없이 입력하세요."
        )
    return value


def route_http_error_message(status_code, payload, fallback):
    messages = {
        401: "REST API 키 인증에 실패했습니다. 키 설정을 확인하세요. (HTTP 401)",
        403: "경로 요청이 거부되었습니다. 앱 권한과 API 사용 설정을 확인하세요. (HTTP 403)",
        429: "경로 요청 한도를 초과했습니다. 잠시 후 다시 시도하세요. (HTTP 429)",
    }
    if status_code in messages:
        return messages[status_code]
    if isinstance(payload, dict):
        for name in ("msg", "message"):
            message = payload.get(name)
            if isinstance(message, str) and message.strip():
                return f"경로 탐색 실패: {message.strip()}"
    return f"경로 탐색 실패: {fallback or f'HTTP {status_code}'}"


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
    except (TypeError, ValueError, OverflowError) as exc:
        raise RouteValidationError(f"{label} 좌표가 올바르지 않습니다.") from exc
    if not math.isfinite(lon) or not math.isfinite(lat):
        raise RouteValidationError(f"{label} 좌표가 올바르지 않습니다.")
    if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
        raise RouteValidationError(f"{label} 좌표가 범위를 벗어났습니다.")
    return lon, lat


def _json_value(raw, default, error_message):
    if raw is None or raw == "":
        return default
    if not isinstance(raw, str):
        raise RouteValidationError(error_message)
    try:
        return json.loads(raw)
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
    priority = (
        priority if isinstance(priority, str) and priority in ROUTE_PRIORITIES
        else "RECOMMEND"
    )

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
    if any(not isinstance(value, str) for value in avoid_data):
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
    except (TypeError, ValueError, OverflowError):
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


# Official types: https://developers.kakaomobility.com/guide/navi-api/reference.html
# Preserve directional icons for sided entrances/exits; roundabouts stay distinct.
GUIDANCE_CATEGORIES = {
    0: "straight", 1: "left", 2: "right", 3: "uturn",
    5: "left", 6: "right", 7: "transition", 8: "left", 9: "right",
    10: "transition", 11: "left", 12: "right",
    14: "transition", 15: "transition", 16: "transition", 17: "transition",
    18: "right", 19: "right", 20: "right", 21: "right", 22: "right",
    23: "other", 24: "left", 25: "left", 26: "left", 27: "left", 28: "left",
    29: "straight",
    **{code: "roundabout" for code in range(30, 42)},
    42: "transition", 43: "left", 44: "right", 45: "transition",
    46: "left", 47: "right", 48: "left", 49: "right",
    61: "transition", 62: "transition",
    **{code: "roundabout" for code in range(70, 82)},
    82: "left", 83: "right", 84: "transition", 85: "transition", 86: "transition",
    100: "start", 101: "destination", 1000: "waypoint",
    300: "transition", 301: "transition",
}


def guidance_category(guide_type, guidance):
    if guide_type in GUIDANCE_CATEGORIES:
        return GUIDANCE_CATEGORIES[guide_type]
    if "유턴" in guidance:
        return "uturn"
    left = "좌회전" in guidance or "왼쪽" in guidance
    right = "우회전" in guidance or "오른쪽" in guidance
    if left and right:
        return "other"
    if left:
        return "left"
    if right:
        return "right"
    if "직진" in guidance:
        return "straight"
    return "other"


def _response_object(value, label):
    if not isinstance(value, dict):
        raise MobilityResponseError(f"경로 응답의 {label} 형식이 올바르지 않습니다.")
    return value


def _response_list(value, label):
    if value is None:
        return []
    if not isinstance(value, list):
        raise MobilityResponseError(f"경로 응답의 {label} 형식이 올바르지 않습니다.")
    return value


def _response_integer(value, label):
    if value is None:
        return 0
    try:
        number = int(value)
        if isinstance(value, bool) or number < 0:
            raise ValueError()
        if isinstance(value, float) and value != number:
            raise ValueError()
    except (TypeError, ValueError, OverflowError) as exc:
        raise MobilityResponseError(f"경로 응답의 {label} 값이 올바르지 않습니다.") from exc
    return number


def _extract_guides(route, route_id):
    guides = []
    cumulative_distance = 0
    cumulative_duration = 0
    for section_index, section in enumerate(route.get("sections") or []):
        # Guidance is optional: skip malformed items without losing valid geometry.
        section_guides = section.get("guides")
        if not isinstance(section_guides, list):
            continue
        for guide in section_guides:
            if not isinstance(guide, dict):
                continue
            try:
                lon, lat = _coordinate(guide["x"], guide["y"], "안내 지점")
                guide_type = int(guide.get("type") or 0)
                distance = _response_integer(guide.get("distance"), "안내 거리")
                duration = _response_integer(guide.get("duration"), "안내 시간")
                road_index = int(guide.get("road_index") or 0)
            except (KeyError, TypeError, ValueError, OverflowError):
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
    payload = _response_object(payload, "결과")
    routes = _response_list(payload.get("routes"), "경로 목록")
    if not routes:
        raise MobilityResponseError("경로 탐색 결과가 없습니다.")
    route = _response_object(routes[0], "경로")
    if route.get("result_code") != 0:
        raise MobilityResponseError(
            str(route.get("result_msg") or "경로를 찾지 못했습니다.")
        )
    points = []
    for section in _response_list(route.get("sections"), "구간 목록"):
        section = _response_object(section, "구간")
        for road in _response_list(section.get("roads"), "도로 목록"):
            road = _response_object(road, "도로")
            vertexes = _response_list(road.get("vertexes"), "선형 좌표")
            if len(vertexes) % 2:
                raise MobilityResponseError("경로 선형 좌표의 개수가 올바르지 않습니다.")
            for index in range(0, len(vertexes) - 1, 2):
                try:
                    point = _coordinate(
                        vertexes[index],
                        vertexes[index + 1],
                        "경로 선형",
                    )
                except RouteValidationError as exc:
                    raise MobilityResponseError("경로 선형 좌표가 올바르지 않습니다.") from exc
                if not points or point != points[-1]:
                    points.append(point)
    if len(points) < 2:
        raise MobilityResponseError("경로 선형 좌표를 찾지 못했습니다.")
    summary = route.get("summary")
    summary = _response_object({} if summary is None else summary, "요약")
    route_id = str(payload.get("trans_id") or uuid4())
    return RouteResultData(
        route_id=route_id,
        points=tuple(points),
        distance=_response_integer(summary.get("distance"), "거리"),
        duration=_response_integer(summary.get("duration"), "시간"),
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
