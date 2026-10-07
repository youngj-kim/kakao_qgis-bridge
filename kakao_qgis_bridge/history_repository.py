"""In-memory QGIS layers used as the route history repository."""

import json

from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer


from .history_formats import HISTORY_SCHEMA_VERSION
from .history_values import safe_number
from .history_operations import HistoryOperations


class HistoryRepository:
    def __init__(self, route_symbol_factory, guidance_renderer_factory):
        self._route_symbol_factory = route_symbol_factory
        self._guidance_renderer_factory = guidance_renderer_factory
        self.route_layer = None
        self.guidance_layer = None
        self._operations = HistoryOperations()

    @property
    def needs_recovery(self):
        return self._operations.needs_recovery

    def clear(self):
        self.route_layer = None
        self.guidance_layer = None
        self._operations = HistoryOperations()

    def ensure_layers(self):
        if self.route_layer is None:
            route_uri = (
                "LineString?crs=EPSG:4326"
                "&field=schema_ver:integer"
                "&field=history_id:string(36)"
                "&field=route_id:string(64)"
                "&field=searched_at:string(32)"
                "&field=origin_lon:double(20,10)"
                "&field=origin_lat:double(20,10)"
                "&field=origin_name:string(255)"
                "&field=destination_lon:double(20,10)"
                "&field=destination_lat:double(20,10)"
                "&field=destination_name:string(255)"
                "&field=waypoints_json:string(4096)"
                "&field=distance_m:integer"
                "&field=duration_s:integer"
                "&field=guidance_count:integer"
                "&field=result_summary:string(255)"
                "&field=priority:string(16)"
                "&field=avoid:string(128)"
                "&field=car_type:integer"
                "&field=car_fuel:string(16)"
                "&field=car_hipass:integer"
            )
            self.route_layer = QgsVectorLayer(
                route_uri,
                "Kakao Route History",
                "memory",
            )
            self.route_layer.renderer().setSymbol(self._route_symbol_factory())

        if self.guidance_layer is None:
            guidance_uri = (
                "Point?crs=EPSG:4326"
                "&field=schema_ver:integer"
                "&field=history_id:string(36)"
                "&field=route_id:string(64)"
                "&field=searched_at:string(32)"
                "&field=sequence:integer"
                "&field=section_no:integer"
                "&field=guide_type:integer"
                "&field=category:string(16)"
                "&field=guidance:string(255)"
                "&field=name:string(128)"
                "&field=distance_m:integer"
                "&field=duration_s:integer"
                "&field=cum_distance_m:integer"
                "&field=cum_duration_s:integer"
                "&field=road_index:integer"
                "&field=longitude:double(20,10)"
                "&field=latitude:double(20,10)"
            )
            self.guidance_layer = QgsVectorLayer(
                guidance_uri,
                "Kakao Guidance History",
                "memory",
            )
            self.guidance_layer.setRenderer(self._guidance_renderer_factory())

        return self.route_layer, self.guidance_layer

    def append(
        self,
        history_id,
        route_id,
        searched_at,
        points,
        origin,
        destination,
        origin_label,
        destination_label,
        waypoints,
        distance,
        duration,
        guidance_count,
        result_summary,
        priority,
        avoid_options,
        vehicle_options,
        guides,
    ):
        route_layer, guidance_layer = self.ensure_layers()
        route_feature = QgsFeature(route_layer.fields())
        route_feature.setGeometry(QgsGeometry.fromPolylineXY(points))
        route_feature.setAttributes(
            [
                HISTORY_SCHEMA_VERSION,
                history_id,
                route_id,
                searched_at,
                origin[0],
                origin[1],
                origin_label,
                destination[0],
                destination[1],
                destination_label,
                json.dumps(waypoints, ensure_ascii=False, separators=(",", ":")),
                distance,
                duration,
                guidance_count,
                result_summary,
                priority,
                "|".join(avoid_options),
                vehicle_options["car_type"],
                vehicle_options["car_fuel"],
                1 if vehicle_options["car_hipass"] else 0,
            ]
        )
        guidance_features = []
        for guide in guides:
            feature = QgsFeature(guidance_layer.fields())
            feature.setGeometry(
                QgsGeometry.fromPointXY(
                    QgsPointXY(guide["longitude"], guide["latitude"])
                )
            )
            feature.setAttributes(
                [
                    HISTORY_SCHEMA_VERSION,
                    history_id,
                    guide["route_id"],
                    searched_at,
                    guide["sequence"],
                    guide["section_no"],
                    guide["guide_type"],
                    guide["category"],
                    guide["guidance"],
                    guide["name"],
                    guide["distance_m"],
                    guide["duration_s"],
                    guide["cumulative_distance_m"],
                    guide["cumulative_duration_s"],
                    guide["road_index"],
                    guide["longitude"],
                    guide["latitude"],
                ]
            )
            guidance_features.append(feature)
        self.add_history_features([route_feature], guidance_features, "이력 추가")
        return True

    def route_for_history(self, history_id):
        if self.route_layer is None:
            return None
        for feature in self.route_layer.getFeatures():
            if str(feature["history_id"]) == history_id:
                return QgsFeature(feature)
        return None

    def guidance_for_history(self, history_id):
        if self.guidance_layer is None:
            return []
        features = [
            feature
            for feature in self.guidance_layer.getFeatures()
            if str(feature["history_id"]) == history_id
        ]
        features.sort(key=lambda feature: safe_number(feature["sequence"]))
        return [QgsFeature(feature) for feature in features]

    def add_history_features(self, routes, guides, operation="이력 불러오기"):
        self._operations.apply(operation, [
            (self.route_layer, routes, []), (self.guidance_layer, guides, []),
        ])
        return len(routes), len(guides)

    def delete_history(self, history_id):
        route = self.route_for_history(history_id)
        if route is None:
            return
        guide_ids = [feature.id() for feature in self.guidance_for_history(history_id)]
        self._operations.apply("선택 이력 삭제", [
            (self.route_layer, [], [route.id()]), (self.guidance_layer, [], guide_ids),
        ])

    def delete_all(self):
        changes = [(layer, [], [feature.id() for feature in layer.getFeatures()])
                   for layer in (self.route_layer, self.guidance_layer) if layer is not None]
        self._operations.apply("전체 이력 삭제", changes)
