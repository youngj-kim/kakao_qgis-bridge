import json
import math

from qgis.core import (
    Qgis,
    QgsCategorizedSymbolRenderer,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsMessageLog,
    QgsPointXY,
    QgsProject,
    QgsProperty,
    QgsRendererCategory,
    QgsSvgMarkerSymbolLayer,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QTimer, Qt, QUrl, QUrlQuery
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from qgis.PyQt.QtWidgets import QInputDialog, QLineEdit, QMessageBox

try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction

from .dock_widget import KakaoMapDockWidget
from .settings import (
    PLUGIN_DIR,
    environment_javascript_key,
    environment_rest_api_key,
    kakao_javascript_key_source,
    kakao_rest_api_key,
    legacy_file_javascript_key,
    save_javascript_key,
    save_rest_api_key,
    stored_javascript_key,
    stored_rest_api_key,
)


MENU_NAME = "&Kakao QGIS Bridge"
LOG_TAG = "Kakao QGIS Bridge"
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


class KakaoQgisBridgePlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.settings_action = None
        self.rest_settings_action = None
        self.dock = None
        self.roadview_layer = None
        self.roadview_feature_id = None
        self.route_layer = None
        self.route_guidance_layer = None
        self.route_guidance_feature_ids = {}
        self.route_points_layer = None
        self.route_point_feature_ids = {}
        self.route_reply = None
        self.network_manager = QNetworkAccessManager()
        self.canvas_sync_connected = False
        self.canvas_sync_timer = QTimer()
        self.canvas_sync_timer.setSingleShot(True)
        self.canvas_sync_timer.setInterval(350)
        self.canvas_sync_timer.timeout.connect(self._sync_canvas_center)
        self.reverse_sync_guard_timer = QTimer()
        self.reverse_sync_guard_timer.setSingleShot(True)
        self.reverse_sync_guard_timer.setInterval(600)

    def initGui(self):
        self.action = QAction(
            QIcon(str(PLUGIN_DIR / "icon.png")),
            "Kakao Map / Roadview",
            self.iface.mainWindow(),
        )
        self.action.setCheckable(True)
        self.action.triggered.connect(self.toggle_dock)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(MENU_NAME, self.action)

        self.settings_action = QAction(
            QIcon.fromTheme("configure"),
            "Kakao JavaScript API 키 설정...",
            self.iface.mainWindow(),
        )
        self.settings_action.triggered.connect(self._configure_api_key)
        self.iface.addPluginToMenu(MENU_NAME, self.settings_action)

        self.rest_settings_action = QAction(
            QIcon.fromTheme("dialog-password"),
            "Kakao REST API 키 설정...",
            self.iface.mainWindow(),
        )
        self.rest_settings_action.triggered.connect(self._configure_rest_api_key)
        self.iface.addPluginToMenu(MENU_NAME, self.rest_settings_action)

    def unload(self):
        self._deactivate_canvas_sync()

        if self.action is not None:
            self.iface.removePluginMenu(MENU_NAME, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None

        if self.settings_action is not None:
            self.iface.removePluginMenu(MENU_NAME, self.settings_action)
            self.settings_action = None

        if self.rest_settings_action is not None:
            self.iface.removePluginMenu(MENU_NAME, self.rest_settings_action)
            self.rest_settings_action = None

        if self.route_reply is not None:
            try:
                self.route_reply.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
            self.route_reply.abort()
            self.route_reply.deleteLater()
            self.route_reply = None

        if self.dock is not None:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None

        self._remove_roadview_layer()
        self._remove_route_layer()
        self._remove_route_guidance_layer()
        self._remove_route_points_layer()

    def toggle_dock(self, checked):
        if checked:
            self._show_dock()
        else:
            self._hide_dock()

    def _show_dock(self):
        if not self._ensure_api_key():
            if self.action is not None:
                self.action.setChecked(False)
            return

        self._ensure_dock()
        self.dock.show()
        self.dock.raise_()
        self._activate_canvas_sync()

    def _ensure_api_key(self):
        source = kakao_javascript_key_source()
        if source in ("environment", "qgis"):
            return True

        # Offer the old settings.json value as a one-time migration path.
        initial_value = legacy_file_javascript_key() if source == "file" else ""
        return self._prompt_and_save_api_key(initial_value)

    def _configure_api_key(self, _checked=False):
        if environment_javascript_key():
            QMessageBox.information(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                "현재 환경변수 KAKAO_MAP_JAVASCRIPT_KEY가 우선 적용되고 있습니다. "
                "환경변수를 변경한 뒤 QGIS를 다시 시작해 주세요.",
            )
            return

        initial_value = stored_javascript_key() or legacy_file_javascript_key()
        if self._prompt_and_save_api_key(initial_value):
            if self.dock is not None:
                self.dock.reload_viewer()
            self.iface.messageBar().pushSuccess(
                "Kakao QGIS Bridge",
                "Kakao JavaScript API 키를 저장하고 뷰어를 다시 불러왔습니다.",
            )

    def _prompt_and_save_api_key(self, initial_value=""):
        value, accepted = QInputDialog.getText(
            self.iface.mainWindow(),
            "Kakao JavaScript API 키",
            "Kakao Developers에서 발급한 JavaScript 키를 입력하세요:",
            QLineEdit.EchoMode.Password,
            initial_value,
        )
        if not accepted:
            return False

        value = value.strip()
        if not value:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                "JavaScript 키를 입력해야 지도를 불러올 수 있습니다.",
            )
            return False

        save_javascript_key(value)
        return True

    def _configure_rest_api_key(self, _checked=False):
        if environment_rest_api_key():
            QMessageBox.information(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                "현재 환경변수 KAKAO_REST_API_KEY가 우선 적용되고 있습니다. "
                "환경변수를 변경한 뒤 QGIS를 다시 시작해 주세요.",
            )
            return

        if self._prompt_and_save_rest_api_key(stored_rest_api_key()):
            self.iface.messageBar().pushSuccess(
                "Kakao QGIS Bridge",
                "Kakao REST API 키를 저장했습니다.",
            )

    def _prompt_and_save_rest_api_key(self, initial_value=""):
        value, accepted = QInputDialog.getText(
            self.iface.mainWindow(),
            "Kakao REST API 키",
            "Kakao Mobility 길찾기에 사용할 REST API 키를 입력하세요:",
            QLineEdit.EchoMode.Password,
            initial_value,
        )
        if not accepted:
            return False

        value = value.strip()
        if not value:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                "REST API 키를 입력해야 경로를 탐색할 수 있습니다.",
            )
            return False

        save_rest_api_key(value)
        return True

    def _hide_dock(self):
        if self.dock is not None:
            self.dock.hide()
        self._deactivate_canvas_sync()

    def _ensure_dock(self):
        if self.dock is not None:
            return

        self.dock = KakaoMapDockWidget(self.iface.mainWindow())
        self.dock.centerRequested.connect(self._handle_viewer_moved)
        self.dock.roadviewStateChanged.connect(self._update_roadview_layer)
        self.dock.routeRequested.connect(self._request_route)
        self.dock.routePointChanged.connect(self._set_route_point)
        self.dock.routePointCleared.connect(self._clear_route_point)
        self.dock.routePointsCleared.connect(self._clear_route_points)
        self.dock.routeGuidanceSelected.connect(self._focus_route_guidance)
        self.dock.visibilityChanged.connect(self._sync_action_state)
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)

    def _sync_action_state(self, visible):
        if self.action is not None:
            self.action.setChecked(visible)

        if visible:
            self._activate_canvas_sync()
        else:
            self._deactivate_canvas_sync()

    def _activate_canvas_sync(self):
        canvas = self.iface.mapCanvas()

        if not self.canvas_sync_connected:
            canvas.extentsChanged.connect(self._schedule_canvas_sync)
            canvas.destinationCrsChanged.connect(self._schedule_canvas_sync)
            self.canvas_sync_connected = True
            self.iface.messageBar().pushInfo(
                "Kakao QGIS Bridge",
                "QGIS 이동은 Kakao에, Roadview 위치 이동은 QGIS에 양방향으로 반영됩니다.",
            )

        self._schedule_canvas_sync()

    def _deactivate_canvas_sync(self):
        canvas = self.iface.mapCanvas()

        self.canvas_sync_timer.stop()
        self.reverse_sync_guard_timer.stop()
        if self.canvas_sync_connected:
            for signal in (canvas.extentsChanged, canvas.destinationCrsChanged):
                try:
                    signal.disconnect(self._schedule_canvas_sync)
                except (RuntimeError, TypeError):
                    pass
            self.canvas_sync_connected = False

    def _schedule_canvas_sync(self, *_args):
        if self.dock is None or not self.dock.isVisible():
            return
        if self.reverse_sync_guard_timer.isActive():
            return
        self.canvas_sync_timer.start()

    def _sync_canvas_center(self):
        if self.dock is None or not self.dock.isVisible():
            return

        canvas = self.iface.mapCanvas()
        try:
            lon, lat = self._to_epsg_4326(canvas.center())
        except Exception as exc:
            QgsMessageLog.logMessage(str(exc), LOG_TAG, Qgis.MessageLevel.Warning)
            self.iface.messageBar().pushWarning(
                "Kakao QGIS Bridge",
                "QGIS 지도 중심 좌표를 EPSG:4326으로 변환하지 못했습니다.",
            )
            return

        self.dock.set_center(lon, lat)

    def _handle_viewer_moved(self, lon, lat):
        if not math.isfinite(lon) or not math.isfinite(lat):
            return
        if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
            return

        canvas = self.iface.mapCanvas()
        source_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        target_crs = canvas.mapSettings().destinationCrs()

        try:
            transform = QgsCoordinateTransform(
                source_crs,
                target_crs,
                QgsProject.instance(),
            )
            center = transform.transform(QgsPointXY(lon, lat))
        except Exception as exc:
            QgsMessageLog.logMessage(str(exc), LOG_TAG, Qgis.MessageLevel.Warning)
            self.iface.messageBar().pushWarning(
                "Kakao QGIS Bridge",
                "Kakao 지도/Roadview 좌표를 QGIS 프로젝트 좌표계로 변환하지 못했습니다.",
            )
            return

        self.canvas_sync_timer.stop()
        self.reverse_sync_guard_timer.start()
        canvas.setCenter(center)
        canvas.refresh()

    def _update_roadview_layer(self, lon, lat, pan, tilt, zoom, pano_id):
        values = (lon, lat, pan, tilt, zoom)
        if not all(math.isfinite(value) for value in values):
            return
        if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
            return

        layer = self._ensure_roadview_layer()
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

    def _ensure_roadview_layer(self):
        project = QgsProject.instance()
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

        svg_path = PLUGIN_DIR / "web" / "roadview_radar.svg"
        symbol = QgsMarkerSymbol(
            [QgsSvgMarkerSymbolLayer(str(svg_path), 24.0)]
        )
        symbol.setDataDefinedAngle(QgsProperty.fromField("pan"))
        layer.renderer().setSymbol(symbol)

        project.addMapLayer(layer)
        self.roadview_layer = layer
        self.roadview_feature_id = None
        return layer

    def _remove_roadview_layer(self):
        if self.roadview_layer is None:
            return

        project = QgsProject.instance()
        try:
            layer_id = self.roadview_layer.id()
            if project.mapLayer(layer_id) is not None:
                project.removeMapLayer(layer_id)
        except RuntimeError:
            pass
        self.roadview_layer = None
        self.roadview_feature_id = None

    def _request_route(
        self,
        origin_lon,
        origin_lat,
        destination_lon,
        destination_lat,
        priority,
        waypoints_json,
        avoid_json,
        vehicle_json,
    ):
        coordinates = (
            origin_lon,
            origin_lat,
            destination_lon,
            destination_lat,
        )
        if not all(math.isfinite(value) for value in coordinates):
            self._set_route_status(False, "출발지 또는 도착지 좌표가 올바르지 않습니다.")
            return
        if (
            not -180.0 <= origin_lon <= 180.0
            or not -90.0 <= origin_lat <= 90.0
            or not -180.0 <= destination_lon <= 180.0
            or not -90.0 <= destination_lat <= 90.0
        ):
            self._set_route_status(False, "출발지 또는 도착지 좌표가 범위를 벗어났습니다.")
            return

        if priority not in ROUTE_PRIORITIES:
            priority = "RECOMMEND"

        try:
            waypoint_data = json.loads(waypoints_json) if waypoints_json else []
        except json.JSONDecodeError:
            self._set_route_status(False, "경유지 정보를 해석하지 못했습니다.")
            return

        if not isinstance(waypoint_data, list):
            self._set_route_status(False, "경유지 정보 형식이 올바르지 않습니다.")
            return
        if len(waypoint_data) > MAX_ROUTE_WAYPOINTS:
            self._set_route_status(
                False,
                f"경유지는 최대 {MAX_ROUTE_WAYPOINTS}개까지 사용할 수 있습니다.",
            )
            return

        try:
            avoid_data = json.loads(avoid_json) if avoid_json else []
        except json.JSONDecodeError:
            self._set_route_status(False, "경로 회피 옵션을 해석하지 못했습니다.")
            return
        if not isinstance(avoid_data, list):
            self._set_route_status(False, "경로 회피 옵션 형식이 올바르지 않습니다.")
            return

        avoid_options = []
        for value in avoid_data:
            if value in ROUTE_AVOID_OPTIONS and value not in avoid_options:
                avoid_options.append(value)

        try:
            vehicle_data = json.loads(vehicle_json) if vehicle_json else {}
        except json.JSONDecodeError:
            self._set_route_status(False, "차량 설정을 해석하지 못했습니다.")
            return
        if not isinstance(vehicle_data, dict):
            self._set_route_status(False, "차량 설정 형식이 올바르지 않습니다.")
            return

        try:
            car_type = int(vehicle_data.get("car_type", 1))
        except (TypeError, ValueError):
            car_type = 1
        if car_type not in ROUTE_CAR_TYPES:
            car_type = 1

        car_fuel = str(vehicle_data.get("car_fuel", "GASOLINE"))
        if car_fuel not in ROUTE_CAR_FUELS:
            car_fuel = "GASOLINE"
        car_hipass = vehicle_data.get("car_hipass") is True
        vehicle_options = {
            "car_type": car_type,
            "car_fuel": car_fuel,
            "car_hipass": car_hipass,
        }

        waypoints = []
        for index, item in enumerate(waypoint_data):
            if not isinstance(item, dict):
                self._set_route_status(False, "경유지 정보 형식이 올바르지 않습니다.")
                return
            try:
                lon = float(item["lon"])
                lat = float(item["lat"])
            except (KeyError, TypeError, ValueError):
                self._set_route_status(False, "경유지 좌표가 올바르지 않습니다.")
                return
            if not math.isfinite(lon) or not math.isfinite(lat):
                self._set_route_status(False, "경유지 좌표가 올바르지 않습니다.")
                return
            if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
                self._set_route_status(False, "경유지 좌표가 범위를 벗어났습니다.")
                return

            point_id = str(item.get("id") or f"waypoint:{index + 1}")
            if not point_id.startswith("waypoint:"):
                point_id = f"waypoint:{index + 1}"
            waypoints.append(
                {
                    "id": point_id,
                    "lon": lon,
                    "lat": lat,
                }
            )

        self._set_route_point("origin", origin_lon, origin_lat)
        self._set_route_point("destination", destination_lon, destination_lat)
        active_waypoint_ids = {waypoint["id"] for waypoint in waypoints}
        for point_id in list(self.route_point_feature_ids):
            if (
                point_id.startswith("waypoint:")
                and point_id not in active_waypoint_ids
            ):
                self._clear_route_point(point_id)
        for waypoint in waypoints:
            self._set_route_point(
                waypoint["id"],
                waypoint["lon"],
                waypoint["lat"],
            )

        rest_key = kakao_rest_api_key()
        if not rest_key:
            if not self._prompt_and_save_rest_api_key():
                self._set_route_status(False, "Kakao REST API 키가 필요합니다.")
                return
            rest_key = kakao_rest_api_key()

        if self.route_reply is not None:
            try:
                self.route_reply.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
            self.route_reply.abort()
            self.route_reply.deleteLater()

        url = QUrl(ROUTE_ENDPOINT)
        query = QUrlQuery()
        query.addQueryItem("origin", f"{origin_lon:.8f},{origin_lat:.8f}")
        query.addQueryItem(
            "destination",
            f"{destination_lon:.8f},{destination_lat:.8f}",
        )
        if waypoints:
            query.addQueryItem(
                "waypoints",
                "|".join(
                    f'{waypoint["lon"]:.8f},{waypoint["lat"]:.8f}'
                    for waypoint in waypoints
                ),
            )
        if avoid_options:
            query.addQueryItem("avoid", "|".join(avoid_options))
        query.addQueryItem("priority", priority)
        query.addQueryItem("car_type", str(car_type))
        query.addQueryItem("car_fuel", car_fuel)
        query.addQueryItem("car_hipass", "true" if car_hipass else "false")
        query.addQueryItem("summary", "false")
        query.addQueryItem("alternatives", "false")
        query.addQueryItem("road_details", "false")
        url.setQuery(query)

        request = QNetworkRequest(url)
        request.setRawHeader(
            b"Authorization",
            f"KakaoAK {rest_key}".encode("ascii"),
        )
        request.setRawHeader(b"Content-Type", b"application/json")

        reply = self.network_manager.get(request)
        self.route_reply = reply
        reply.finished.connect(
            lambda current_reply=reply: self._handle_route_reply(
                current_reply,
                priority,
                len(waypoints),
                avoid_options,
                vehicle_options,
            )
        )

    def _handle_route_reply(
        self,
        reply,
        priority,
        waypoint_count,
        avoid_options,
        vehicle_options,
    ):
        if reply is not self.route_reply:
            reply.deleteLater()
            return

        self.route_reply = None
        status_code = reply.attribute(
            QNetworkRequest.Attribute.HttpStatusCodeAttribute
        )
        raw_data = bytes(reply.readAll())
        network_error = reply.error()
        network_error_message = reply.errorString()
        reply.deleteLater()

        try:
            payload = json.loads(raw_data.decode("utf-8")) if raw_data else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}

        if (
            network_error != QNetworkReply.NetworkError.NoError
            or status_code != 200
        ):
            message = (
                payload.get("msg")
                or payload.get("message")
                or network_error_message
                or f"HTTP {status_code}"
            )
            self._set_route_status(False, f"경로 탐색 실패: {message}")
            return

        routes = payload.get("routes") or []
        if not routes:
            self._set_route_status(False, "경로 탐색 결과가 없습니다.")
            return

        route = routes[0]
        if route.get("result_code") != 0:
            self._set_route_status(
                False,
                route.get("result_msg") or "경로를 찾지 못했습니다.",
            )
            return

        points = []
        for section in route.get("sections") or []:
            for road in section.get("roads") or []:
                vertexes = road.get("vertexes") or []
                for index in range(0, len(vertexes) - 1, 2):
                    try:
                        point = QgsPointXY(
                            float(vertexes[index]),
                            float(vertexes[index + 1]),
                        )
                    except (TypeError, ValueError):
                        continue
                    if not points or point != points[-1]:
                        points.append(point)

        if len(points) < 2:
            self._set_route_status(False, "경로 선형 좌표를 찾지 못했습니다.")
            return

        summary = route.get("summary") or {}
        distance = int(summary.get("distance") or 0)
        duration = int(summary.get("duration") or 0)
        route_id = str(payload.get("trans_id") or "current")
        guides = self._extract_route_guides(route, route_id)
        self._create_route_layer(
            points,
            distance,
            duration,
            priority,
            waypoint_count,
            avoid_options,
            vehicle_options,
        )
        guidance_payload = {
            "route_id": route_id,
            "summary": {
                "distance_m": distance,
                "duration_s": duration,
                "priority": priority,
                "waypoint_count": waypoint_count,
                "avoid": avoid_options,
                "vehicle": vehicle_options,
            },
            "guides": guides,
        }
        self._create_route_guidance_layer(guides)
        if self.dock is not None:
            self.dock.set_route_guidance(guidance_payload)

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
        self._set_route_status(True, message)
        self.iface.messageBar().pushSuccess("Kakao QGIS Bridge", message)

    def _extract_route_guides(self, route, route_id):
        guides = []
        cumulative_distance = 0
        cumulative_duration = 0

        for section_index, section in enumerate(route.get("sections") or []):
            for guide in section.get("guides") or []:
                try:
                    lon = float(guide["x"])
                    lat = float(guide["y"])
                    guide_type = int(guide.get("type") or 0)
                    distance = max(0, int(guide.get("distance") or 0))
                    duration = max(0, int(guide.get("duration") or 0))
                    road_index = int(guide.get("road_index") or 0)
                except (KeyError, TypeError, ValueError):
                    continue
                if not math.isfinite(lon) or not math.isfinite(lat):
                    continue
                if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
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
                        "category": self._guidance_category(
                            guide_type,
                            guidance,
                        ),
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

        return guides

    @staticmethod
    def _guidance_category(guide_type, guidance):
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
            1, 5, 8, 11, 24, 25, 26, 27, 28,
            43, 46, 48, 76, 77, 78, 79, 80, 82,
        } or "좌회전" in guidance or "왼쪽" in guidance:
            return "left"
        if guide_type in {
            2, 6, 9, 12, 18, 19, 20, 21, 22,
            44, 47, 49, 70, 71, 72, 73, 74, 83,
        } or "우회전" in guidance or "오른쪽" in guidance:
            return "right"
        if guide_type in {0, 29} or "직진" in guidance:
            return "straight"
        if guide_type in {
            7, 8, 9, 10, 11, 12, 14, 15, 16, 17,
            42, 43, 44, 45, 46, 47, 48, 49,
            61, 62, 84, 85, 86, 300, 301,
        }:
            return "transition"
        return "other"

    def _create_route_layer(
        self,
        points,
        distance,
        duration,
        priority,
        waypoint_count,
        avoid_options,
        vehicle_options,
    ):
        self._remove_route_layer()

        uri = (
            "LineString?crs=EPSG:4326"
            "&field=distance_m:integer"
            "&field=duration_s:integer"
            "&field=priority:string(16)"
            "&field=waypoint_count:integer"
            "&field=avoid:string(128)"
            "&field=car_type:integer"
            "&field=car_fuel:string(16)"
            "&field=car_hipass:integer"
        )
        layer = QgsVectorLayer(uri, "Kakao Mobility Route", "memory")
        layer.setCustomProperty("skipMemoryLayersCheck", 1)
        layer.renderer().setSymbol(
            QgsLineSymbol.createSimple(
                {
                    "line_color": "#1976d2",
                    "line_width": "1.4",
                }
            )
        )

        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPolylineXY(points))
        feature.setAttributes(
            [
                distance,
                duration,
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

        project = QgsProject.instance()
        project.addMapLayer(layer)
        self.route_layer = layer

        canvas = self.iface.mapCanvas()
        try:
            transform = QgsCoordinateTransform(
                layer.crs(),
                canvas.mapSettings().destinationCrs(),
                project,
            )
            extent = transform.transformBoundingBox(layer.extent())
            margin = max(extent.width(), extent.height()) * 0.08
            if margin > 0:
                extent.grow(margin)
            canvas.setExtent(extent)
        except Exception as exc:
            QgsMessageLog.logMessage(str(exc), LOG_TAG, Qgis.MessageLevel.Warning)
        canvas.refresh()

    def _remove_route_layer(self):
        if self.route_layer is None:
            return

        project = QgsProject.instance()
        try:
            layer_id = self.route_layer.id()
            if project.mapLayer(layer_id) is not None:
                project.removeMapLayer(layer_id)
        except RuntimeError:
            pass
        self.route_layer = None

    def _create_route_guidance_layer(self, guides):
        self._remove_route_guidance_layer()
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

        renderer = QgsCategorizedSymbolRenderer(
            "category",
            [
                QgsRendererCategory(
                    "start",
                    self._route_pin_symbol("route_origin_pin.svg", 7.5),
                    "출발",
                ),
                QgsRendererCategory(
                    "destination",
                    self._route_pin_symbol(
                        "route_destination_pin.svg",
                        7.5,
                    ),
                    "도착",
                ),
                QgsRendererCategory(
                    "waypoint",
                    self._route_pin_symbol("route_waypoint_pin.svg", 7.5),
                    "경유지",
                ),
                QgsRendererCategory(
                    "straight",
                    self._guidance_symbol("guidance_straight.svg"),
                    "직진",
                ),
                QgsRendererCategory(
                    "left",
                    self._guidance_symbol("guidance_left.svg"),
                    "좌회전",
                ),
                QgsRendererCategory(
                    "right",
                    self._guidance_symbol("guidance_right.svg"),
                    "우회전",
                ),
                QgsRendererCategory(
                    "uturn",
                    self._guidance_symbol("guidance_uturn.svg"),
                    "유턴",
                ),
                QgsRendererCategory(
                    "roundabout",
                    self._guidance_symbol("guidance_roundabout.svg"),
                    "회전교차로",
                ),
                QgsRendererCategory(
                    "transition",
                    self._guidance_symbol("guidance_transition.svg"),
                    "진출입",
                ),
                QgsRendererCategory(
                    "other",
                    self._guidance_symbol("guidance_other.svg"),
                    "기타 안내",
                ),
            ],
        )
        layer.setRenderer(renderer)

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
        QgsProject.instance().addMapLayer(layer)
        self.route_guidance_layer = layer
        self.route_guidance_feature_ids = feature_ids

    @staticmethod
    def _guidance_symbol(filename):
        svg_path = PLUGIN_DIR / "web" / filename
        return QgsMarkerSymbol([QgsSvgMarkerSymbolLayer(str(svg_path), 6.5)])

    def _focus_route_guidance(self, sequence, lon, lat):
        if not math.isfinite(lon) or not math.isfinite(lat):
            return
        if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
            return

        if self.route_guidance_layer is not None:
            try:
                feature_id = self.route_guidance_feature_ids.get(sequence)
                self.route_guidance_layer.removeSelection()
                if feature_id is not None:
                    self.route_guidance_layer.selectByIds([feature_id])
            except RuntimeError:
                self.route_guidance_layer = None
                self.route_guidance_feature_ids = {}

        self._handle_viewer_moved(lon, lat)

    def _remove_route_guidance_layer(self):
        if self.route_guidance_layer is None:
            self.route_guidance_feature_ids = {}
            return

        project = QgsProject.instance()
        try:
            layer_id = self.route_guidance_layer.id()
            if project.mapLayer(layer_id) is not None:
                project.removeMapLayer(layer_id)
        except RuntimeError:
            pass
        self.route_guidance_layer = None
        self.route_guidance_feature_ids = {}

    def _set_route_point(self, point_id, lon, lat):
        role = self._route_point_role(point_id)
        if role is None:
            return
        if not math.isfinite(lon) or not math.isfinite(lat):
            return
        if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
            return

        layer = self._ensure_route_points_layer()
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
        layer.triggerRepaint()

    def _ensure_route_points_layer(self):
        project = QgsProject.instance()
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

        origin_symbol = self._route_pin_symbol("route_origin_pin.svg")
        destination_symbol = self._route_pin_symbol(
            "route_destination_pin.svg"
        )
        waypoint_symbol = self._route_pin_symbol("route_waypoint_pin.svg")
        renderer = QgsCategorizedSymbolRenderer(
            "role",
            [
                QgsRendererCategory("origin", origin_symbol, "출발지"),
                QgsRendererCategory(
                    "destination",
                    destination_symbol,
                    "도착지",
                ),
                QgsRendererCategory(
                    "waypoint",
                    waypoint_symbol,
                    "경유지",
                ),
            ],
        )
        layer.setRenderer(renderer)

        project.addMapLayer(layer)
        self.route_points_layer = layer
        self.route_point_feature_ids = {}
        return layer

    @staticmethod
    def _route_pin_symbol(filename, size=9.0):
        svg_path = PLUGIN_DIR / "web" / filename
        symbol_layer = QgsSvgMarkerSymbolLayer(str(svg_path), size)
        symbol_layer.setVerticalAnchorPoint(Qgis.VerticalAnchorPoint.Bottom)
        return QgsMarkerSymbol([symbol_layer])

    @staticmethod
    def _route_point_role(point_id):
        if point_id in ("origin", "destination"):
            return point_id
        if point_id.startswith("waypoint:"):
            return "waypoint"
        return None

    def _clear_route_point(self, point_id):
        if self._route_point_role(point_id) is None:
            return

        feature_id = self.route_point_feature_ids.pop(point_id, None)
        if feature_id is None or self.route_points_layer is None:
            return

        try:
            self.route_points_layer.dataProvider().deleteFeatures([feature_id])
            self.route_points_layer.updateExtents()
            self.route_points_layer.triggerRepaint()
        except RuntimeError:
            self.route_points_layer = None
            self.route_point_feature_ids = {}

    def _clear_route_points(self):
        feature_ids = list(self.route_point_feature_ids.values())
        self.route_point_feature_ids = {}
        if not feature_ids or self.route_points_layer is None:
            return

        try:
            self.route_points_layer.dataProvider().deleteFeatures(feature_ids)
            self.route_points_layer.updateExtents()
            self.route_points_layer.triggerRepaint()
        except RuntimeError:
            self.route_points_layer = None

    def _remove_route_points_layer(self):
        if self.route_points_layer is None:
            self.route_point_feature_ids = {}
            return

        project = QgsProject.instance()
        try:
            layer_id = self.route_points_layer.id()
            if project.mapLayer(layer_id) is not None:
                project.removeMapLayer(layer_id)
        except RuntimeError:
            pass
        self.route_points_layer = None
        self.route_point_feature_ids = {}

    def _set_route_status(self, success, message):
        if self.dock is not None:
            self.dock.set_route_status(success, message)

    def _to_epsg_4326(self, point):
        canvas = self.iface.mapCanvas()
        source_crs = canvas.mapSettings().destinationCrs()
        target_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
        transformed = transform.transform(point)
        return transformed.x(), transformed.y()
