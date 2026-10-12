"""Coordinate validated route requests and results through explicit callbacks."""

from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from uuid import uuid4

from qgis.core import QgsPointXY

from .mobility import (
    ROUTE_AVOID_OPTIONS, ROUTE_CAR_FUELS, ROUTE_CAR_TYPES, ROUTE_PRIORITIES,
    RouteValidationError, normalize_route_request, route_result_summary,
)


@dataclass(frozen=True)
class RouteCallbacks:
    transitioning: Callable
    current_epoch: Callable
    point_ids: Callable
    rest_key: Callable
    prompt_rest_key: Callable
    submit: Callable
    status: Callable
    set_point: Callable
    clear_point: Callable
    create_route: Callable
    create_guidance: Callable
    show_points: Callable
    append_history: Callable
    guidance: Callable
    path_payload: Callable
    set_active_history: Callable
    notify: Callable


class RouteController:
    """Request/result orchestration; client lifetime and project epochs stay at the boundary."""

    def __init__(self, callbacks):
        self.callbacks = callbacks

    def request(
        self,
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
        if self.callbacks.transitioning():
            return
        epoch = self.callbacks.current_epoch()
        try:
            route_request = normalize_route_request(
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
            )
        except RouteValidationError as exc:
            self.callbacks.status(False, str(exc))
            return

        origin_lon, origin_lat = route_request.origin
        destination_lon, destination_lat = route_request.destination
        waypoints = route_request.waypoints

        self.callbacks.set_point("origin", origin_lon, origin_lat)
        self.callbacks.set_point("destination", destination_lon, destination_lat)
        active_waypoint_ids = {waypoint["id"] for waypoint in waypoints}
        for point_id in list(self.callbacks.point_ids()):
            if (
                point_id.startswith("waypoint:")
                and point_id not in active_waypoint_ids
            ):
                self.callbacks.clear_point(point_id)
        for waypoint in waypoints:
            self.callbacks.set_point(
                waypoint["id"],
                waypoint["lon"],
                waypoint["lat"],
            )

        rest_key = self.callbacks.rest_key()
        if not rest_key:
            if not self.callbacks.prompt_rest_key():
                self.callbacks.status(False, "Kakao REST API 키가 필요합니다.")
                return
            rest_key = self.callbacks.rest_key()

        if epoch != self.callbacks.current_epoch():
            return
        self.callbacks.submit(rest_key, route_request, epoch)

    def handle_result(self, result, route_request):
        epoch = self.callbacks.current_epoch()
        points = [QgsPointXY(lon, lat) for lon, lat in result.points]
        distance = result.distance
        duration = result.duration
        priority = route_request.priority
        waypoints = route_request.waypoints
        avoid_options = route_request.avoid_options
        vehicle_options = route_request.vehicle_options
        origin = route_request.origin
        destination = route_request.destination
        origin_label = route_request.origin_label
        destination_label = route_request.destination_label
        waypoint_count = len(waypoints)
        route_id = result.route_id
        history_id = str(uuid4())
        searched_at = datetime.now().astimezone().isoformat(timespec="seconds")
        guides = list(result.guides)
        guidance_count = len(guides)
        result_summary = route_result_summary(
            distance,
            duration,
            vehicle_options["car_type"],
            guidance_count,
        )
        self.callbacks.create_route(
            points,
            distance,
            duration,
            guidance_count,
            result_summary,
            priority,
            waypoint_count,
            avoid_options,
            vehicle_options,
        )
        guidance_payload = {
            "history_id": history_id,
            "route_id": route_id,
            "summary": {
                "distance_m": distance,
                "duration_s": duration,
                "guidance_count": guidance_count,
                "result_summary": result_summary,
                "priority": priority,
                "waypoint_count": waypoint_count,
                "avoid": avoid_options,
                "vehicle": vehicle_options,
            },
            "origin": {
                "label": origin_label,
                "lon": origin[0],
                "lat": origin[1],
            },
            "destination": {
                "label": destination_label,
                "lon": destination[0],
                "lat": destination[1],
            },
            "waypoints": [
                {
                    "label": waypoint.get("label", ""),
                    "lon": waypoint.get("lon"),
                    "lat": waypoint.get("lat"),
                }
                for waypoint in waypoints
            ],
            "path": self.callbacks.path_payload(points),
            "guides": guides,
        }
        self.callbacks.create_guidance(guides)
        self.callbacks.show_points(points, guides, waypoints)
        self.callbacks.set_active_history(None)
        history_saved = self.callbacks.append_history(
            history_id=history_id,
            route_id=route_id,
            searched_at=searched_at,
            points=points,
            origin=origin,
            destination=destination,
            origin_label=origin_label,
            destination_label=destination_label,
            waypoints=waypoints,
            distance=distance,
            duration=duration,
            guidance_count=guidance_count,
            result_summary=result_summary,
            priority=priority,
            avoid_options=avoid_options,
            vehicle_options=vehicle_options,
            guides=guides,
        )
        if epoch != self.callbacks.current_epoch():
            return
        if history_saved:
            self.callbacks.set_active_history(history_id)
        else:
            guidance_payload["history_id"] = ""
        self.callbacks.guidance(guidance_payload)

        distance_text = f"{distance / 1000:.1f} km"
        duration_text = f"{max(1, round(duration / 60))}분"
        priority_text = ROUTE_PRIORITIES.get(priority, ROUTE_PRIORITIES["RECOMMEND"])
        waypoint_text = f", 경유지 {waypoint_count}개" if waypoint_count else ""
        avoid_text = ""
        if avoid_options:
            labels = [ROUTE_AVOID_OPTIONS[value] for value in avoid_options]
            avoid_text = f", 회피: {', '.join(labels)}"
        vehicle_text = (
            f", 차량: {ROUTE_CAR_TYPES[vehicle_options['car_type']]}/"
            f"{ROUTE_CAR_FUELS[vehicle_options['car_fuel']]}"
        )
        if vehicle_options["car_hipass"]:
            vehicle_text += "/하이패스"
        message = (
            f"{priority_text} 경로 생성 완료: {distance_text}, "
            f"예상 {duration_text}{waypoint_text}{avoid_text}{vehicle_text}"
        )
        if history_saved:
            self.callbacks.status(True, message)
            self.callbacks.notify(True, message)
        else:
            message = "경로는 생성했지만 이력 저장에 실패했습니다. " + message
            self.callbacks.status(False, message)
            self.callbacks.notify(False, message)
