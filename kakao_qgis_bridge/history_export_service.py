"""Write route history files independently of plugin UI and lifecycle.

Layers and transform context are supplied by the caller. Only GPX exports need
the two style factories; each invocation creates fresh QGIS symbol objects.
"""
import math
from datetime import datetime

from qgis.core import QgsFeature, QgsVectorLayer, QgsVectorFileWriter, QgsVariantUtils
from .compat import (
    WRITE_APPEND_ADD_FIELDS, WRITE_APPEND_NO_FIELDS,
    WRITE_OVERWRITE_FILE, WRITE_OVERWRITE_LAYER, save_style_to_database,
)
from .history_export import GpxWriter, shapefile_text
from .history_formats import paired_output_paths, full_history_field_specs
from . import history_values


class HistoryExportService:
    def __init__(self, transform_context, route_line_symbol_factory=None,
                 gpx_waypoint_renderer_factory=None):
        self.transform_context = transform_context
        self.route_line_symbol_factory = route_line_symbol_factory
        self.gpx_waypoint_renderer_factory = gpx_waypoint_renderer_factory

    _safe_number = staticmethod(history_values.safe_number)
    _safe_float = staticmethod(history_values.safe_float)
    _route_points_from_geometry = staticmethod(history_values.route_points_from_geometry)
    _waypoints_from_history = staticmethod(history_values.waypoints_from_history)

    @staticmethod
    def _geojson_output_paths(filename):
        return HistoryExportService._paired_output_paths(filename, ".geojson")

    @staticmethod
    def _paired_output_paths(filename, extension):
        return paired_output_paths(filename, extension)

    def write_geojson_layer(
        self,
        source_layer,
        output_path,
        layer_name,
    ):
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GeoJSON"
        options.fileEncoding = "UTF-8"
        options.layerName = layer_name
        options.actionOnExistingFile = (
            WRITE_OVERWRITE_FILE
        )
        options.layerOptions = [
            "RFC7946=YES",
            "COORDINATE_PRECISION=8",
            "WRITE_BBOX=YES",
            "AUTODETECT_JSON_STRINGS=NO",
        ]

        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            source_layer,
            str(output_path),
            self.transform_context,
            options,
        )
        error_code = result[0] if isinstance(result, tuple) else result
        error_value = getattr(error_code, "value", error_code)
        if int(error_value) != 0:
            error_message = ""
            if isinstance(result, tuple) and len(result) > 1:
                error_message = str(result[1] or "")
            detail = error_message or f"오류 코드 {error_value}"
            raise RuntimeError(
                f"{output_path.name} 저장 실패: {detail}"
            )

        self._save_sidecar_style(
            output_path,
            layer_name,
            source_layer,
        )
        return source_layer.featureCount()

    def write_shapefile_layer(
        self,
        source_layer,
        output_path,
        geometry_name,
        layer_name,
        field_specs,
    ):
        shapefile_layer = self._shapefile_compatible_layer(
            source_layer,
            geometry_name,
            field_specs,
        )

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "ESRI Shapefile"
        options.fileEncoding = "UTF-8"
        options.layerName = layer_name
        options.actionOnExistingFile = (
            WRITE_OVERWRITE_FILE
        )
        options.layerOptions = ["ENCODING=UTF-8"]

        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            shapefile_layer,
            str(output_path),
            self.transform_context,
            options,
        )
        error_code = result[0] if isinstance(result, tuple) else result
        error_value = getattr(error_code, "value", error_code)
        if int(error_value) != 0:
            error_message = ""
            if isinstance(result, tuple) and len(result) > 1:
                error_message = str(result[1] or "")
            detail = error_message or f"오류 코드 {error_value}"
            raise RuntimeError(
                f"{output_path.name} 저장 실패: {detail}"
            )

        self._save_sidecar_style(
            output_path,
            layer_name,
            source_layer,
        )
        return shapefile_layer.featureCount()

    def write_gpx(self, route_layer, guidance_layer, output_path):
        if not callable(self.route_line_symbol_factory) or not callable(self.gpx_waypoint_renderer_factory):
            raise RuntimeError("GPX 내보내기에 필요한 스타일 생성기가 없습니다.")
        writer = GpxWriter()
        writer.start(
            "gpx",
            {
                "xmlns": "http://www.topografix.com/GPX/1/1",
                "xmlns:kakao": "https://yjkim.dev/kakao-qgis-bridge",
                "version": "1.1",
                "creator": "Kakao QGIS Bridge",
            },
        )

        writer.start("metadata")
        self._gpx_text(writer, "name", "Kakao QGIS Bridge Route History")
        self._gpx_text(
            writer,
            "time",
            datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        writer.end("metadata")

        route_features = list(route_layer.getFeatures())
        guidance_by_history = self._guidance_features_by_history(guidance_layer)
        route_total = 0
        guidance_total = 0

        for route_feature in route_features:
            points = self._route_points_from_geometry(route_feature.geometry())
            if len(points) < 2:
                continue

            route_total += 1
            history_id = str(route_feature["history_id"] or "")
            name = self._gpx_route_name(route_feature)
            desc = str(route_feature["result_summary"] or "")
            guides = guidance_by_history.get(history_id, [])
            guidance_total += len(guides)

            self._append_gpx_waypoints(writer, route_feature, guides)
            self._append_gpx_track(writer, name, desc, route_feature, points)
            self._append_gpx_route(writer, name, desc, route_feature, points)

        writer.end("gpx")
        try:
            output_path.write_text(writer.document(), encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"{output_path.name} 저장 실패: {exc}") from exc

        self._save_gpx_sidecar_styles(output_path)
        return route_total, guidance_total

    def _save_gpx_sidecar_styles(self, output_path):
        tracks_layer = QgsVectorLayer(
            "LineString?crs=EPSG:4326&field=name:string(255)&field=type:string(32)",
            "Kakao GPX Tracks",
            "memory",
        )
        tracks_layer.renderer().setSymbol(self.route_line_symbol_factory())
        self._save_layer_style_to_path(
            tracks_layer,
            output_path.with_name(f"{output_path.stem}_tracks.qml"),
        )

        routes_layer = QgsVectorLayer(
            "LineString?crs=EPSG:4326&field=name:string(255)&field=type:string(32)",
            "Kakao GPX Routes",
            "memory",
        )
        routes_layer.renderer().setSymbol(self.route_line_symbol_factory())
        self._save_layer_style_to_path(
            routes_layer,
            output_path.with_name(f"{output_path.stem}_routes.qml"),
        )

        waypoints_layer = QgsVectorLayer(
            "Point?crs=EPSG:4326&field=name:string(255)&field=type:string(64)",
            "Kakao GPX Waypoints",
            "memory",
        )
        waypoints_layer.setRenderer(self.gpx_waypoint_renderer_factory())
        self._save_layer_style_to_path(
            waypoints_layer,
            output_path.with_name(f"{output_path.stem}_waypoints.qml"),
        )

    @staticmethod
    def _save_layer_style_to_path(layer, style_path):
        error_message, success = layer.saveNamedStyle(str(style_path))
        if not success:
            detail = error_message or "알 수 없는 오류"
            raise RuntimeError(
                f"{style_path.name} 스타일 저장 실패: {detail}"
            )

    @staticmethod
    def _guidance_features_by_history(guidance_layer):
        grouped = {}
        if guidance_layer is None:
            return grouped
        for feature in guidance_layer.getFeatures():
            history_id = str(feature["history_id"] or "")
            if not history_id:
                continue
            grouped.setdefault(history_id, []).append(QgsFeature(feature))
        for features in grouped.values():
            features.sort(
                key=lambda feature: HistoryExportService._safe_number(
                    feature["sequence"]
                )
            )
        return grouped

    def _append_gpx_waypoints(self, writer, route_feature, guide_features):
        history_id = str(route_feature["history_id"] or "")
        self._append_gpx_wpt(
            writer,
            self._safe_float(route_feature["origin_lon"]),
            self._safe_float(route_feature["origin_lat"]),
            str(route_feature["origin_name"] or "출발지"),
            "origin",
            history_id,
            "출발지",
        )

        for index, waypoint in enumerate(
            self._waypoints_from_history(route_feature),
            start=1,
        ):
            self._append_gpx_wpt(
                writer,
                self._safe_float(waypoint.get("lon")),
                self._safe_float(waypoint.get("lat")),
                str(waypoint.get("label") or f"경유지 {index}"),
                "waypoint",
                history_id,
                f"경유지 {index}",
            )

        self._append_gpx_wpt(
            writer,
            self._safe_float(route_feature["destination_lon"]),
            self._safe_float(route_feature["destination_lat"]),
            str(route_feature["destination_name"] or "도착지"),
            "destination",
            history_id,
            "도착지",
        )

        for guide in guide_features:
            sequence = self._safe_number(guide["sequence"])
            self._append_gpx_wpt(
                writer,
                self._safe_float(guide["longitude"]),
                self._safe_float(guide["latitude"]),
                f"{sequence}. {guide['guidance']}",
                f"guidance:{guide['category']}",
                history_id,
                str(guide["name"] or "경로 안내"),
                {
                    "sequence": sequence,
                    "guide_type": self._safe_number(guide["guide_type"]),
                    "distance_m": self._safe_number(guide["distance_m"]),
                    "duration_s": self._safe_number(guide["duration_s"]),
                },
            )

    def _append_gpx_track(self, writer, name, desc, route_feature, points):
        writer.start("trk")
        self._gpx_text(writer, "name", name)
        if desc:
            self._gpx_text(writer, "desc", desc)
        self._append_gpx_extensions(writer, route_feature)
        writer.start("trkseg")
        for point in points:
            writer.empty(
                "trkpt",
                {
                    "lat": f"{point.y():.8f}",
                    "lon": f"{point.x():.8f}",
                },
            )
        writer.end("trkseg")
        writer.end("trk")

    def _append_gpx_route(self, writer, name, desc, route_feature, points):
        writer.start("rte")
        self._gpx_text(writer, "name", name)
        if desc:
            self._gpx_text(writer, "desc", desc)
        self._append_gpx_extensions(writer, route_feature)
        for point in points:
            writer.empty(
                "rtept",
                {
                    "lat": f"{point.y():.8f}",
                    "lon": f"{point.x():.8f}",
                },
            )
        writer.end("rte")

    def _append_gpx_wpt(
        self,
        writer,
        lon,
        lat,
        name,
        point_type,
        history_id,
        desc="",
        extra=None,
    ):
        if not math.isfinite(lon) or not math.isfinite(lat):
            return
        if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
            return

        writer.start(
            "wpt",
            {
                "lat": f"{lat:.8f}",
                "lon": f"{lon:.8f}",
            },
        )
        self._gpx_text(writer, "name", name)
        if desc:
            self._gpx_text(writer, "desc", desc)
        self._gpx_text(writer, "type", point_type)

        writer.start("extensions")
        self._gpx_kakao_text(writer, "history_id", history_id)
        if extra:
            for key, value in extra.items():
                self._gpx_kakao_text(writer, key, value)
        writer.end("extensions")
        writer.end("wpt")

    def _append_gpx_extensions(self, writer, route_feature):
        writer.start("extensions")
        for key in (
            "history_id",
            "route_id",
            "searched_at",
            "distance_m",
            "duration_s",
            "guidance_count",
            "priority",
            "avoid",
            "car_type",
            "car_fuel",
            "car_hipass",
        ):
            self._gpx_kakao_text(writer, key, route_feature[key])
        writer.end("extensions")

    @staticmethod
    def _gpx_text(writer, tag, value):
        writer.text(tag, value)

    @staticmethod
    def _gpx_kakao_text(writer, tag, value):
        writer.text(f"kakao:{tag}", value if value is not None else "")

    @staticmethod
    def _gpx_route_name(route_feature):
        origin = str(route_feature["origin_name"] or "출발지")
        destination = str(route_feature["destination_name"] or "도착지")
        return f"{origin} → {destination}"

    @staticmethod
    def shapefile_loss_counts(source_layer, field_specs):
        """Count affected values without storing text or changing source data."""
        counts = {}
        string_specs = [spec for spec in field_specs if spec["type"] == "string"
                        and spec["source"] in source_layer.fields().names()]
        for feature in source_layer.getFeatures():
            for spec in string_specs:
                value = feature[spec["source"]]
                if QgsVariantUtils.isNull(value):
                    continue
                text = str(value)
                if shapefile_text(text, spec["length"]) != text:
                    counts[spec["source"]] = counts.get(spec["source"], 0) + 1
        return counts

    @staticmethod
    def _shapefile_compatible_layer(
        source_layer,
        geometry_name,
        field_specs,
    ):
        field_parts = []
        for spec in field_specs:
            field_type = spec["type"]
            if field_type == "string":
                field_parts.append(
                    f"&field={spec['name']}:string({spec['length']})"
                )
            elif field_type == "double":
                field_parts.append(f"&field={spec['name']}:double(20,10)")
            else:
                field_parts.append(f"&field={spec['name']}:integer")

        uri = (
            f"{geometry_name}?crs={source_layer.crs().authid()}"
            + "".join(field_parts)
        )
        layer = QgsVectorLayer(uri, "Kakao History Shapefile Export", "memory")
        provider = layer.dataProvider()
        source_field_names = set(source_layer.fields().names())

        features = []
        for source_feature in source_layer.getFeatures():
            feature = QgsFeature(layer.fields())
            feature.setGeometry(source_feature.geometry())
            attributes = []
            for spec in field_specs:
                source_name = spec["source"]
                value = (
                    source_feature[source_name]
                    if source_name in source_field_names
                    else None
                )
                if not QgsVariantUtils.isNull(value) and spec["type"] == "string":
                    value = shapefile_text(value, spec["length"])
                attributes.append(value)
            feature.setAttributes(attributes)
            features.append(feature)

        if features:
            provider.addFeatures(features)
            layer.updateExtents()
        return layer

    @staticmethod
    def _shapefile_sidecar_paths(path):
        return [
            path.with_suffix(extension)
            for extension in (
                ".shp",
                ".shx",
                ".dbf",
                ".prj",
                ".cpg",
                ".qix",
                ".qml",
            )
        ]

    @staticmethod
    def _route_shapefile_fields():
        names = {spec["source"]: spec["name"] for spec in full_history_field_specs("route")}
        field_specs = [
            {'source': 'schema_ver', 'type': 'integer'},
            {'source': 'history_id', 'type': 'string', 'length': 36},
            {'source': 'route_id', 'type': 'string', 'length': 64},
            {'source': 'searched_at', 'type': 'string', 'length': 32},
            {'source': 'origin_lon', 'type': 'double'},
            {'source': 'origin_lat', 'type': 'double'},
            {'source': 'origin_name', 'type': 'string', 'length': 254},
            {'source': 'destination_lon', 'type': 'double'},
            {'source': 'destination_lat', 'type': 'double'},
            {'source': 'destination_name', 'type': 'string', 'length': 254},
            {'source': 'waypoints_json', 'type': 'string', 'length': 254},
            {'source': 'distance_m', 'type': 'integer'},
            {'source': 'duration_s', 'type': 'integer'},
            {'source': 'guidance_count', 'type': 'integer'},
            {'source': 'result_summary', 'type': 'string', 'length': 254},
            {'source': 'priority', 'type': 'string', 'length': 16},
            {'source': 'avoid', 'type': 'string', 'length': 128},
            {'source': 'car_type', 'type': 'integer'},
            {'source': 'car_fuel', 'type': 'string', 'length': 16},
            {'source': 'car_hipass', 'type': 'integer'},
        ]
        return [{"name": names[spec["source"]], **spec} for spec in field_specs]

    @staticmethod
    def _guidance_shapefile_fields():
        names = {spec["source"]: spec["name"] for spec in full_history_field_specs("guidance")}
        field_specs = [
            {'source': 'schema_ver', 'type': 'integer'},
            {'source': 'history_id', 'type': 'string', 'length': 36},
            {'source': 'route_id', 'type': 'string', 'length': 64},
            {'source': 'searched_at', 'type': 'string', 'length': 32},
            {'source': 'sequence', 'type': 'integer'},
            {'source': 'section_no', 'type': 'integer'},
            {'source': 'guide_type', 'type': 'integer'},
            {'source': 'category', 'type': 'string', 'length': 16},
            {'source': 'guidance', 'type': 'string', 'length': 254},
            {'source': 'name', 'type': 'string', 'length': 128},
            {'source': 'distance_m', 'type': 'integer'},
            {'source': 'duration_s', 'type': 'integer'},
            {'source': 'cum_distance_m', 'type': 'integer'},
            {'source': 'cum_duration_s', 'type': 'integer'},
            {'source': 'road_index', 'type': 'integer'},
            {'source': 'longitude', 'type': 'double'},
            {'source': 'latitude', 'type': 'double'},
        ]
        return [{"name": names[spec["source"]], **spec} for spec in field_specs]

    @staticmethod
    def _save_sidecar_style(
        output_path,
        layer_name,
        source_layer,
    ):
        layer = QgsVectorLayer(str(output_path), layer_name, "ogr")
        if not layer.isValid():
            raise RuntimeError(
                f"{output_path.name}을 열어 QML 스타일을 저장하지 못했습니다."
            )

        layer.setRenderer(source_layer.renderer().clone())
        style_path = output_path.with_suffix(".qml")
        error_message, success = layer.saveNamedStyle(str(style_path))
        if not success:
            detail = error_message or "알 수 없는 오류"
            raise RuntimeError(
                f"{style_path.name} 스타일 저장 실패: {detail}"
            )

    def write_geopackage_layer(
        self,
        source_layer,
        output_path,
        layer_name,
        geometry_name,
    ):
        (
            layer_exists,
            existing_ids,
            existing_fields,
        ) = self._existing_history_ids(output_path, layer_name)
        source_fields = {field.name() for field in source_layer.fields()}
        missing_fields = source_fields - existing_fields
        pending_layer = self._history_layer_subset(
            source_layer,
            existing_ids,
            geometry_name,
        )
        pending_count = pending_layer.featureCount()
        if pending_count == 0 and layer_exists and not missing_fields:
            self._save_history_layer_style(
                output_path,
                layer_name,
                source_layer,
            )
            return 0

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.fileEncoding = "UTF-8"
        options.layerName = layer_name

        if layer_exists:
            options.actionOnExistingFile = (
                WRITE_APPEND_ADD_FIELDS
                if missing_fields
                else WRITE_APPEND_NO_FIELDS
            )
        elif output_path.exists():
            options.actionOnExistingFile = (
                WRITE_OVERWRITE_LAYER
            )
            options.layerOptions = ["SPATIAL_INDEX=YES"]
        else:
            options.actionOnExistingFile = (
                WRITE_OVERWRITE_FILE
            )
            options.layerOptions = ["SPATIAL_INDEX=YES"]

        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            pending_layer,
            str(output_path),
            self.transform_context,
            options,
        )
        error_code = result[0] if isinstance(result, tuple) else result
        error_value = getattr(error_code, "value", error_code)
        if int(error_value) != 0:
            error_message = ""
            if isinstance(result, tuple) and len(result) > 1:
                error_message = str(result[1] or "")
            detail = error_message or f"오류 코드 {error_value}"
            raise RuntimeError(f"{layer_name} 레이어 저장 실패: {detail}")

        self._save_history_layer_style(
            output_path,
            layer_name,
            source_layer,
        )

        return pending_count

    @staticmethod
    def _save_history_layer_style(output_path, layer_name, source_layer):
        layer = QgsVectorLayer(
            f"{output_path}|layername={layer_name}",
            layer_name,
            "ogr",
        )
        if not layer.isValid():
            raise RuntimeError(
                f"{layer_name} 레이어를 열어 기본 스타일을 저장하지 못했습니다."
            )

        layer.setRenderer(source_layer.renderer().clone())
        success, error_message = save_style_to_database(
            layer,
            "Kakao QGIS Bridge",
            "Kakao QGIS Bridge route history default style",
            True,
        )
        if not success:
            detail = error_message or "알 수 없는 오류"
            raise RuntimeError(
                f"{layer_name} 기본 스타일 저장 실패: {detail}"
            )

    @staticmethod
    def _existing_history_ids(output_path, layer_name):
        if not output_path.exists():
            return False, set(), set()

        layer = QgsVectorLayer(
            f"{output_path}|layername={layer_name}",
            layer_name,
            "ogr",
        )
        if not layer.isValid():
            return False, set(), set()

        history_index = layer.fields().indexOf("history_id")
        if history_index < 0:
            raise RuntimeError(
                f"기존 {layer_name} 레이어에 history_id 필드가 없습니다."
            )
        history_ids = {
            str(feature[history_index])
            for feature in layer.getFeatures()
            if feature[history_index]
        }
        field_names = {field.name() for field in layer.fields()}
        return True, history_ids, field_names

    @staticmethod
    def _history_layer_subset(source_layer, existing_ids, geometry_name):
        subset = QgsVectorLayer(
            f"{geometry_name}?crs={source_layer.crs().authid()}",
            "Kakao History Export",
            "memory",
        )
        provider = subset.dataProvider()
        provider.addAttributes(list(source_layer.fields()))
        subset.updateFields()

        features = []
        for source_feature in source_layer.getFeatures():
            if str(source_feature["history_id"]) in existing_ids:
                continue
            feature = QgsFeature(subset.fields())
            feature.setGeometry(source_feature.geometry())
            feature.setAttributes(source_feature.attributes())
            features.append(feature)

        if features:
            provider.addFeatures(features)
            subset.updateExtents()
        return subset
