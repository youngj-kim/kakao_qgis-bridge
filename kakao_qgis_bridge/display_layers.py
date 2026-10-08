"""Own current map display layers without controlling UI, canvas or history."""
import math
from qgis.core import QgsCategorizedSymbolRenderer, QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer


class DisplayLayerManager:
    def __init__(self, project, style_factory):
        self.project = project
        self.style_factory = style_factory
        self.forget_all()

    def forget_all(self):
        """Release stale references after the project has removed its layers."""
        self.roadview_layer = None
        self.roadview_feature_id = None
        self.route_layer = None
        self.route_guidance_layer = None
        self.route_guidance_feature_ids = {}
        self.route_points_layer = None
        self.route_point_feature_ids = {}
        self.route_point_categories = {}

    def update_roadview_layer(self, lon, lat, pan, tilt, zoom, pano_id):
        values = (lon, lat, pan, tilt, zoom)
        if not all(math.isfinite(value) for value in values):
            return
        if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
            return

        layer = self.ensure_roadview_layer()
        provider = layer.dataProvider()
        geometry = QgsGeometry.fromPointXY(QgsPointXY(lon, lat))
        attributes = [pano_id, lon, lat, pan, tilt, zoom]

        feature_valid = (
            self.roadview_feature_id is not None
            and layer.getFeature(self.roadview_feature_id).isValid()
        )
        if not feature_valid:
            feature = QgsFeature(layer.fields())
            feature.setGeometry(geometry)
            feature.setAttributes(attributes)
            if provider.addFeature(feature):
                self.roadview_feature_id = feature.id()
        else:
            provider.changeGeometryValues(
                {self.roadview_feature_id: geometry}
            )
            provider.changeAttributeValues(
                {
                    self.roadview_feature_id: {
                        index: value
                        for index, value in enumerate(attributes)
                    }
                }
            )

        layer.updateExtents()
        layer.triggerRepaint()

    def ensure_roadview_layer(self):
        project = self.project
        if self.roadview_layer is not None:
            try:
                if project.mapLayer(self.roadview_layer.id()) is not None:
                    return self.roadview_layer
            except RuntimeError:
                pass

        uri = (
            "Point?crs=EPSG:4326"
            "&field=pano_id:string(32)"
            "&field=longitude:double"
            "&field=latitude:double"
            "&field=pan:double"
            "&field=tilt:double"
            "&field=zoom:double"
        )
        layer = QgsVectorLayer(uri, "Kakao Roadview Position", "memory")
        layer.setCustomProperty("skipMemoryLayersCheck", 1)

        layer.renderer().setSymbol(self.style_factory.roadview_symbol())

        project.addMapLayer(layer)
        self.roadview_layer = layer
        self.roadview_feature_id = None
        return layer

    def remove_roadview_layer(self):
        if self.roadview_layer is None:
            return

        project = self.project
        try:
            layer_id = self.roadview_layer.id()
            if project.mapLayer(layer_id) is not None:
                project.removeMapLayer(layer_id)
        except RuntimeError:
            pass
        self.roadview_layer = None
        self.roadview_feature_id = None

    def create_route_layer(
        self,
        points,
        distance,
        duration,
        guidance_count,
        result_summary,
        priority,
        waypoint_count,
        avoid_options,
        vehicle_options,
    ):
        self.remove_route_layer()

        uri = (
            "LineString?crs=EPSG:4326"
            "&field=distance_m:integer"
            "&field=duration_s:integer"
            "&field=guidance_count:integer"
            "&field=result_summary:string(255)"
            "&field=priority:string(16)"
            "&field=waypoint_count:integer"
            "&field=avoid:string(128)"
            "&field=car_type:integer"
            "&field=car_fuel:string(16)"
            "&field=car_hipass:integer"
        )
        layer = QgsVectorLayer(uri, "Kakao Mobility Route", "memory")
        layer.setCustomProperty("skipMemoryLayersCheck", 1)
        layer.renderer().setSymbol(self.style_factory.route_line_symbol())

        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPolylineXY(points))
        feature.setAttributes(
            [
                distance,
                duration,
                guidance_count,
                result_summary,
                priority,
                waypoint_count,
                "|".join(avoid_options),
                vehicle_options["car_type"],
                vehicle_options["car_fuel"],
                1 if vehicle_options["car_hipass"] else 0,
            ]
        )
        layer.dataProvider().addFeature(feature)
        layer.updateExtents()

        project = self.project
        project.addMapLayer(layer)
        self.route_layer = layer

        return layer

    def remove_route_layer(self):
        if self.route_layer is None:
            return

        project = self.project
        try:
            layer_id = self.route_layer.id()
            if project.mapLayer(layer_id) is not None:
                project.removeMapLayer(layer_id)
        except RuntimeError:
            pass
        self.route_layer = None

    def create_route_guidance_layer(self, guides):
        self.remove_route_guidance_layer()
        if not guides:
            return

        uri = (
            "Point?crs=EPSG:4326"
            "&field=route_id:string(64)"
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
            "&field=longitude:double"
            "&field=latitude:double"
        )
        layer = QgsVectorLayer(uri, "Kakao Route Guidance", "memory")
        layer.setCustomProperty("skipMemoryLayersCheck", 1)
        layer.setRenderer(self.style_factory.route_guidance_renderer())

        provider = layer.dataProvider()
        feature_ids = {}
        for guide in guides:
            feature = QgsFeature(layer.fields())
            feature.setGeometry(
                QgsGeometry.fromPointXY(
                    QgsPointXY(guide["longitude"], guide["latitude"])
                )
            )
            feature.setAttributes(
                [
                    guide["route_id"],
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
            if provider.addFeature(feature):
                feature_ids[guide["sequence"]] = feature.id()

        layer.updateExtents()
        self.project.addMapLayer(layer)
        self.route_guidance_layer = layer
        self.route_guidance_feature_ids = feature_ids

    def remove_route_guidance_layer(self):
        if self.route_guidance_layer is None:
            self.route_guidance_feature_ids = {}
            return

        project = self.project
        try:
            layer_id = self.route_guidance_layer.id()
            if project.mapLayer(layer_id) is not None:
                project.removeMapLayer(layer_id)
        except RuntimeError:
            pass
        self.route_guidance_layer = None
        self.route_guidance_feature_ids = {}

    def set_route_point(self, point_id, lon, lat):
        role = self.route_point_role(point_id)
        if role is None:
            return
        if not math.isfinite(lon) or not math.isfinite(lat):
            return
        if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
            return

        layer = self.ensure_route_points_layer()
        provider = layer.dataProvider()
        geometry = QgsGeometry.fromPointXY(QgsPointXY(lon, lat))
        attributes = [point_id, role, lon, lat]
        feature_id = self.route_point_feature_ids.get(point_id)
        feature_valid = (
            feature_id is not None and layer.getFeature(feature_id).isValid()
        )

        if feature_valid:
            provider.changeGeometryValues({feature_id: geometry})
            provider.changeAttributeValues(
                {
                    feature_id: {
                        index: value
                        for index, value in enumerate(attributes)
                    }
                }
            )
        else:
            feature = QgsFeature(layer.fields())
            feature.setGeometry(geometry)
            feature.setAttributes(attributes)
            if provider.addFeature(feature):
                self.route_point_feature_ids[point_id] = feature.id()

        layer.updateExtents()
        self.sync_route_point_legend()
        layer.triggerRepaint()

    def ensure_route_points_layer(self):
        project = self.project
        if self.route_points_layer is not None:
            try:
                if project.mapLayer(self.route_points_layer.id()) is not None:
                    return self.route_points_layer
            except RuntimeError:
                pass

        uri = (
            "Point?crs=EPSG:4326"
            "&field=point_id:string(32)"
            "&field=role:string(16)"
            "&field=longitude:double"
            "&field=latitude:double"
        )
        layer = QgsVectorLayer(uri, "Kakao Route Points", "memory")
        layer.setCustomProperty("skipMemoryLayersCheck", 1)

        renderer = self.style_factory.route_point_renderer()
        self.route_point_categories = {
            category.value(): category for category in renderer.categories()
        }
        renderer.deleteAllCategories()
        layer.setRenderer(renderer)

        project.addMapLayer(layer)
        self.route_points_layer = layer
        self.route_point_feature_ids = {}
        return layer

    def sync_route_point_legend(self):
        layer = self.route_points_layer
        if layer is None:
            return
        renderer = layer.renderer()
        if not isinstance(renderer, QgsCategorizedSymbolRenderer) or renderer.classAttribute() != "role":
            return
        # Keep edited symbols, labels and visibility when a role disappears and
        # is later added again. A custom non-role renderer is left untouched.
        for category in renderer.categories():
            self.route_point_categories[category.value()] = category
        present_roles = {str(feature["role"]) for feature in layer.getFeatures()}
        updated = renderer.clone()
        updated.deleteAllCategories()
        for role in ("origin", "destination", "waypoint"):
            if role in present_roles:
                updated.addCategory(self.route_point_categories[role])
        layer.setRenderer(updated)

    @staticmethod
    def route_point_role(point_id):
        if point_id in ("origin", "destination"):
            return point_id
        if point_id.startswith("waypoint:"):
            return "waypoint"
        return None

    def clear_route_point(self, point_id):
        if self.route_point_role(point_id) is None:
            return

        feature_id = self.route_point_feature_ids.pop(point_id, None)
        if feature_id is None or self.route_points_layer is None:
            return

        try:
            self.route_points_layer.dataProvider().deleteFeatures([feature_id])
            self.route_points_layer.updateExtents()
            self.sync_route_point_legend()
            self.route_points_layer.triggerRepaint()
        except RuntimeError:
            self.route_points_layer = None
            self.route_point_feature_ids = {}

    def clear_route_points(self):
        feature_ids = list(self.route_point_feature_ids.values())
        self.route_point_feature_ids = {}
        if not feature_ids or self.route_points_layer is None:
            return

        try:
            self.route_points_layer.dataProvider().deleteFeatures(feature_ids)
            self.route_points_layer.updateExtents()
            self.sync_route_point_legend()
            self.route_points_layer.triggerRepaint()
        except RuntimeError:
            self.route_points_layer = None

    def remove_route_points_layer(self):
        if self.route_points_layer is None:
            self.route_point_feature_ids = {}
            return

        project = self.project
        try:
            layer_id = self.route_points_layer.id()
            if project.mapLayer(layer_id) is not None:
                project.removeMapLayer(layer_id)
        except RuntimeError:
            pass
        self.route_points_layer = None
        self.route_point_feature_ids = {}
        self.route_point_categories = {}

    def select_guidance(self, sequence):
        if self.route_guidance_layer is not None:
            try:
                feature_id = self.route_guidance_feature_ids.get(sequence)
                self.route_guidance_layer.removeSelection()
                if feature_id is not None:
                    self.route_guidance_layer.selectByIds([feature_id])
            except RuntimeError:
                self.route_guidance_layer = None
                self.route_guidance_feature_ids = {}

    def remove_all(self):
        self.remove_roadview_layer()
        self.remove_route_layer()
        self.remove_route_guidance_layer()
        self.remove_route_points_layer()
