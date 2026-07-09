import json
import math
from base64 import b64encode
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET
from uuid import uuid4

from qgis.core import (
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
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QTimer, Qt, QUrl, QUrlQuery
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from qgis.PyQt.QtWidgets import QFileDialog, QInputDialog, QLineEdit, QMessageBox

try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction

from .compat import (
    MSGBOX_NO,
    MSGBOX_YES,
    MSG_CRITICAL,
    MSG_WARNING,
    WRITE_APPEND_ADD_FIELDS,
    WRITE_APPEND_NO_FIELDS,
    WRITE_OVERWRITE_FILE,
    WRITE_OVERWRITE_LAYER,
    save_style_to_database,
)
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
HISTORY_SCHEMA_VERSION = 2
ROUTE_HISTORY_LAYER_NAME = "kakao_route_history"
GUIDANCE_HISTORY_LAYER_NAME = "kakao_guidance_history"


class KakaoQgisBridgePlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.settings_action = None
        self.rest_settings_action = None
        self.load_history_action = None
        self.load_gpx_action = None
        self.save_history_action = None
        self.export_geojson_action = None
        self.export_shapefile_action = None
        self.export_gpx_action = None
        self.dock = None
        self.roadview_layer = None
        self.roadview_feature_id = None
        self.route_layer = None
        self.route_guidance_layer = None
        self.route_guidance_feature_ids = {}
        self.route_points_layer = None
        self.route_point_feature_ids = {}
        self.route_history_layer = None
        self.guidance_history_layer = None
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

        self.load_history_action = QAction(
            QIcon.fromTheme("document-open"),
            "경로 이력 불러오기...",
            self.iface.mainWindow(),
        )
        self.load_history_action.triggered.connect(self._load_route_history_file)
        self.iface.addPluginToMenu(MENU_NAME, self.load_history_action)

        self.load_gpx_action = QAction(
            QIcon.fromTheme("document-open"),
            "GPX 스타일 적용해서 불러오기...",
            self.iface.mainWindow(),
        )
        self.load_gpx_action.triggered.connect(self._load_styled_gpx)
        self.iface.addPluginToMenu(MENU_NAME, self.load_gpx_action)

        self.save_history_action = QAction(
            QIcon.fromTheme("document-save-as"),
            "경로 이력 GeoPackage 저장...",
            self.iface.mainWindow(),
        )
        self.save_history_action.setEnabled(False)
        self.save_history_action.triggered.connect(
            self._save_route_history_geopackage
        )
        self.iface.addPluginToMenu(MENU_NAME, self.save_history_action)

        self.export_geojson_action = QAction(
            QIcon.fromTheme("document-export"),
            "경로·안내 이력 GeoJSON 내보내기...",
            self.iface.mainWindow(),
        )
        self.export_geojson_action.setEnabled(False)
        self.export_geojson_action.triggered.connect(
            self._export_route_history_geojson
        )
        self.iface.addPluginToMenu(MENU_NAME, self.export_geojson_action)

        self.export_shapefile_action = QAction(
            QIcon.fromTheme("document-export"),
            "경로·안내 이력 Shapefile 내보내기...",
            self.iface.mainWindow(),
        )
        self.export_shapefile_action.setEnabled(False)
        self.export_shapefile_action.triggered.connect(
            self._export_route_history_shapefile
        )
        self.iface.addPluginToMenu(MENU_NAME, self.export_shapefile_action)

        self.export_gpx_action = QAction(
            QIcon.fromTheme("document-export"),
            "경로·안내 이력 GPX 내보내기...",
            self.iface.mainWindow(),
        )
        self.export_gpx_action.setEnabled(False)
        self.export_gpx_action.triggered.connect(
            self._export_route_history_gpx
        )
        self.iface.addPluginToMenu(MENU_NAME, self.export_gpx_action)

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

        if self.load_history_action is not None:
            self.iface.removePluginMenu(MENU_NAME, self.load_history_action)
            self.load_history_action = None

        if self.load_gpx_action is not None:
            self.iface.removePluginMenu(MENU_NAME, self.load_gpx_action)
            self.load_gpx_action = None

        if self.save_history_action is not None:
            self.iface.removePluginMenu(MENU_NAME, self.save_history_action)
            self.save_history_action = None

        if self.export_geojson_action is not None:
            self.iface.removePluginMenu(MENU_NAME, self.export_geojson_action)
            self.export_geojson_action = None

        if self.export_shapefile_action is not None:
            self.iface.removePluginMenu(
                MENU_NAME,
                self.export_shapefile_action,
            )
            self.export_shapefile_action = None

        if self.export_gpx_action is not None:
            self.iface.removePluginMenu(MENU_NAME, self.export_gpx_action)
            self.export_gpx_action = None

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
        self.route_history_layer = None
        self.guidance_history_layer = None

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
        self.dock.routeHistorySelected.connect(self._focus_route_history)
        self.dock.routeHistoryLoadRequested.connect(self._load_route_history)
        self.dock.routeHistoryDeleteRequested.connect(self._delete_route_history)
        self.dock.routeHistoryExportRequested.connect(self._export_single_route_history)
        self.dock.visibilityChanged.connect(self._sync_action_state)
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        QTimer.singleShot(800, self._sync_route_history_panel)

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
            QgsMessageLog.logMessage(str(exc), LOG_TAG, MSG_WARNING)
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
            QgsMessageLog.logMessage(str(exc), LOG_TAG, MSG_WARNING)
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
        origin_label,
        destination_label,
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
                    "label": str(item.get("label") or "").strip()[:255],
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
                waypoints,
                avoid_options,
                vehicle_options,
                (origin_lon, origin_lat),
                (destination_lon, destination_lat),
                str(origin_label).strip()[:255],
                str(destination_label).strip()[:255],
            )
        )

    def _handle_route_reply(
        self,
        reply,
        priority,
        waypoints,
        avoid_options,
        vehicle_options,
        origin,
        destination,
        origin_label,
        destination_label,
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
        waypoint_count = len(waypoints)
        route_id = str(payload.get("trans_id") or uuid4())
        history_id = str(uuid4())
        searched_at = datetime.now().astimezone().isoformat(timespec="seconds")
        guides = self._extract_route_guides(route, route_id)
        guidance_count = len(guides)
        result_summary = self._route_result_summary(
            distance,
            duration,
            vehicle_options["car_type"],
            guidance_count,
        )
        self._create_route_layer(
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
            "guides": guides,
        }
        self._create_route_guidance_layer(guides)
        self._append_route_history(
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

    def _append_route_history(
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
        route_layer, guidance_layer = self._ensure_route_history_layers()

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
                json.dumps(
                    waypoints,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
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
        if not route_layer.dataProvider().addFeature(route_feature):
            QgsMessageLog.logMessage(
                "경로 검색 이력을 메모리 레이어에 추가하지 못했습니다.",
                LOG_TAG,
                MSG_WARNING,
            )
            return
        route_layer.updateExtents()

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

        if guidance_features:
            guidance_layer.dataProvider().addFeatures(guidance_features)
            guidance_layer.updateExtents()

        if self.save_history_action is not None:
            self.save_history_action.setEnabled(True)
        if self.export_geojson_action is not None:
            self.export_geojson_action.setEnabled(True)
        if self.export_shapefile_action is not None:
            self.export_shapefile_action.setEnabled(True)
        if self.export_gpx_action is not None:
            self.export_gpx_action.setEnabled(True)
        self._sync_route_history_panel(history_id)

    def _ensure_route_history_layers(self):
        if self.route_history_layer is None:
            route_uri = (
                "LineString?crs=EPSG:4326"
                "&field=schema_ver:integer"
                "&field=history_id:string(36)"
                "&field=route_id:string(64)"
                "&field=searched_at:string(32)"
                "&field=origin_lon:double"
                "&field=origin_lat:double"
                "&field=origin_name:string(255)"
                "&field=destination_lon:double"
                "&field=destination_lat:double"
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
            self.route_history_layer = QgsVectorLayer(
                route_uri,
                "Kakao Route History",
                "memory",
            )
            self.route_history_layer.renderer().setSymbol(
                self._route_line_symbol()
            )

        if self.guidance_history_layer is None:
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
                "&field=longitude:double"
                "&field=latitude:double"
            )
            self.guidance_history_layer = QgsVectorLayer(
                guidance_uri,
                "Kakao Guidance History",
                "memory",
            )
            self.guidance_history_layer.setRenderer(
                self._route_guidance_renderer()
            )

        return self.route_history_layer, self.guidance_history_layer

    def _load_route_history_file(self, _checked=False):
        project_home = QgsProject.instance().homePath()
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            "경로 이력 불러오기",
            project_home or "",
            (
                "경로 이력 (*.gpkg *.geojson *.shp);;"
                "GeoPackage (*.gpkg);;"
                "GeoJSON (*.geojson);;"
                "Shapefile (*.shp)"
            ),
        )
        if not filename:
            return

        input_path = Path(filename)
        try:
            route_source, guidance_source = self._open_history_sources(
                input_path
            )
            route_count = self._append_imported_history(
                route_source,
                self.route_history_layer,
                "LineString",
                self._full_history_field_specs("route"),
            )
            guidance_count = self._append_imported_history(
                guidance_source,
                self.guidance_history_layer,
                "Point",
                self._full_history_field_specs("guidance"),
            )
        except RuntimeError as exc:
            QgsMessageLog.logMessage(
                str(exc),
                LOG_TAG,
                MSG_CRITICAL,
            )
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                f"경로 이력 불러오기에 실패했습니다.\n\n{exc}",
            )
            return

        self._update_history_action_state()
        self._sync_route_history_panel()
        if route_count == 0 and guidance_count == 0:
            message = "선택한 파일의 이력이 이미 현재 세션에 있습니다."
        else:
            message = (
                f"경로 이력 불러오기 완료: 경로 {route_count}건, "
                f"안내 {guidance_count}건"
        )
        self.iface.messageBar().pushSuccess("Kakao QGIS Bridge", message)

    def _load_styled_gpx(self, _checked=False):
        project_home = QgsProject.instance().homePath()
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            "GPX 스타일 적용해서 불러오기",
            project_home or "",
            "GPX (*.gpx)",
        )
        if not filename:
            return

        gpx_path = Path(filename)
        if gpx_path.suffix.lower() != ".gpx":
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                "GPX 파일을 선택해 주세요.",
            )
            return

        loaded_layers = []
        missing_styles = []
        try:
            for layer_name, suffix in (
                ("tracks", "_tracks.qml"),
                ("routes", "_routes.qml"),
                ("waypoints", "_waypoints.qml"),
            ):
                layer = QgsVectorLayer(
                    f"{gpx_path}|layername={layer_name}",
                    f"{gpx_path.stem}_{layer_name}",
                    "ogr",
                )
                if not layer.isValid() or layer.featureCount() == 0:
                    continue

                style_path = gpx_path.with_name(f"{gpx_path.stem}{suffix}")
                if style_path.exists():
                    error_message, success = layer.loadNamedStyle(str(style_path))
                    if not success:
                        raise RuntimeError(
                            f"{style_path.name} 스타일 적용 실패: "
                            f"{error_message or '알 수 없는 오류'}"
                        )
                else:
                    missing_styles.append(style_path.name)

                QgsProject.instance().addMapLayer(layer)
                loaded_layers.append(layer)
        except RuntimeError as exc:
            QgsMessageLog.logMessage(
                str(exc),
                LOG_TAG,
                MSG_CRITICAL,
            )
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                f"GPX 불러오기에 실패했습니다.\n\n{exc}",
            )
            return

        if not loaded_layers:
            QMessageBox.information(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                "불러올 GPX tracks/routes/waypoints 레이어가 없습니다.",
            )
            return

        self._zoom_to_layers(loaded_layers)
        message = f"GPX 레이어 {len(loaded_layers)}개를 스타일과 함께 불러왔습니다."
        if missing_styles:
            message += f" 누락된 QML: {', '.join(missing_styles)}"
        self.iface.messageBar().pushSuccess("Kakao QGIS Bridge", message)

    def _open_history_sources(self, input_path):
        suffix = input_path.suffix.lower()
        if suffix == ".gpkg":
            route_source = QgsVectorLayer(
                f"{input_path}|layername={ROUTE_HISTORY_LAYER_NAME}",
                ROUTE_HISTORY_LAYER_NAME,
                "ogr",
            )
            guidance_source = QgsVectorLayer(
                f"{input_path}|layername={GUIDANCE_HISTORY_LAYER_NAME}",
                GUIDANCE_HISTORY_LAYER_NAME,
                "ogr",
            )
        elif suffix == ".geojson":
            route_path, guidance_path = self._geojson_output_paths(input_path)
            route_source = QgsVectorLayer(
                str(route_path),
                "Kakao Route History",
                "ogr",
            )
            guidance_source = QgsVectorLayer(
                str(guidance_path),
                "Kakao Guidance History",
                "ogr",
            )
        elif suffix == ".shp":
            route_path, guidance_path = self._paired_output_paths(
                input_path,
                ".shp",
            )
            route_source = QgsVectorLayer(
                str(route_path),
                "Kakao Route History",
                "ogr",
            )
            guidance_source = QgsVectorLayer(
                str(guidance_path),
                "Kakao Guidance History",
                "ogr",
            )
        else:
            raise RuntimeError("지원하지 않는 이력 파일 형식입니다.")

        if not route_source.isValid():
            raise RuntimeError("경로 이력 레이어를 열지 못했습니다.")
        if not guidance_source.isValid():
            raise RuntimeError("안내 이력 레이어를 열지 못했습니다.")

        self._ensure_route_history_layers()
        return route_source, guidance_source

    def _append_imported_history(
        self,
        source_layer,
        target_layer,
        geometry_name,
        field_specs,
    ):
        existing_ids = self._memory_history_ids(target_layer)
        pending_layer = QgsVectorLayer(
            f"{geometry_name}?crs=EPSG:4326",
            "Imported Kakao Route History",
            "memory",
        )
        provider = pending_layer.dataProvider()
        provider.addAttributes(list(target_layer.fields()))
        pending_layer.updateFields()

        source_fields = set(source_layer.fields().names())
        features = []
        for source_feature in source_layer.getFeatures():
            history_id = self._history_value(
                source_feature,
                source_fields,
                "history_id",
                "hist_id",
            )
            if not history_id or str(history_id) in existing_ids:
                continue

            feature = QgsFeature(pending_layer.fields())
            feature.setGeometry(source_feature.geometry())
            feature.setAttributes(
                [
                    self._history_value(
                        source_feature,
                        source_fields,
                        spec["source"],
                        spec["name"],
                    )
                    for spec in field_specs
                ]
            )
            features.append(feature)

        if features:
            provider.addFeatures(features)
            pending_layer.updateExtents()
            target_layer.dataProvider().addFeatures(features)
            target_layer.updateExtents()

        return len(features)

    @staticmethod
    def _memory_history_ids(layer):
        history_index = layer.fields().indexOf("history_id")
        if history_index < 0:
            return set()
        return {
            str(feature[history_index])
            for feature in layer.getFeatures()
            if feature[history_index]
        }

    @staticmethod
    def _history_value(feature, source_fields, full_name, short_name):
        if full_name in source_fields:
            return feature[full_name]
        if short_name in source_fields:
            return feature[short_name]
        return None

    def _full_history_field_specs(self, layer_type):
        if layer_type == "route":
            return [
                {"source": "schema_ver", "name": "schema_v"},
                {"source": "history_id", "name": "hist_id"},
                {"source": "route_id", "name": "route_id"},
                {"source": "searched_at", "name": "searched"},
                {"source": "origin_lon", "name": "org_lon"},
                {"source": "origin_lat", "name": "org_lat"},
                {"source": "origin_name", "name": "org_name"},
                {"source": "destination_lon", "name": "dst_lon"},
                {"source": "destination_lat", "name": "dst_lat"},
                {"source": "destination_name", "name": "dst_name"},
                {"source": "waypoints_json", "name": "waypts"},
                {"source": "distance_m", "name": "dist_m"},
                {"source": "duration_s", "name": "dur_s"},
                {"source": "guidance_count", "name": "guide_cnt"},
                {"source": "result_summary", "name": "summary"},
                {"source": "priority", "name": "priority"},
                {"source": "avoid", "name": "avoid"},
                {"source": "car_type", "name": "car_type"},
                {"source": "car_fuel", "name": "car_fuel"},
                {"source": "car_hipass", "name": "car_hipass"},
            ]
        return [
            {"source": "schema_ver", "name": "schema_v"},
            {"source": "history_id", "name": "hist_id"},
            {"source": "route_id", "name": "route_id"},
            {"source": "searched_at", "name": "searched"},
            {"source": "sequence", "name": "seq"},
            {"source": "section_no", "name": "sect_no"},
            {"source": "guide_type", "name": "g_type"},
            {"source": "category", "name": "category"},
            {"source": "guidance", "name": "guidance"},
            {"source": "name", "name": "name"},
            {"source": "distance_m", "name": "dist_m"},
            {"source": "duration_s", "name": "dur_s"},
            {"source": "cum_distance_m", "name": "cum_dist"},
            {"source": "cum_duration_s", "name": "cum_dur"},
            {"source": "road_index", "name": "road_idx"},
            {"source": "longitude", "name": "lon"},
            {"source": "latitude", "name": "lat"},
        ]

    def _sync_route_history_panel(self, selected_history_id=None):
        if self.dock is None:
            return
        payload = self._route_history_payload(selected_history_id)
        self.dock.set_route_history(payload)

    def _route_history_payload(self, selected_history_id=None):
        if self.route_history_layer is None:
            return {
                "selected_history_id": selected_history_id or "",
                "items": [],
            }

        history_index = self.route_history_layer.fields().indexOf("history_id")
        items = []
        for feature in self.route_history_layer.getFeatures():
            history_id = str(feature[history_index] or "")
            if not history_id:
                continue
            items.append(
                {
                    "history_id": history_id,
                    "searched_at": str(feature["searched_at"] or ""),
                    "origin_name": str(feature["origin_name"] or "출발지"),
                    "destination_name": str(
                        feature["destination_name"] or "도착지"
                    ),
                    "distance_m": self._safe_number(feature["distance_m"]),
                    "duration_s": self._safe_number(feature["duration_s"]),
                    "guidance_count": self._safe_number(
                        feature["guidance_count"]
                    ),
                    "result_summary": str(feature["result_summary"] or ""),
                    "priority": str(feature["priority"] or ""),
                    "avoid": str(feature["avoid"] or ""),
                    "car_type": self._safe_number(feature["car_type"]),
                    "car_fuel": str(feature["car_fuel"] or ""),
                    "car_hipass": bool(self._safe_number(feature["car_hipass"])),
                }
            )

        items.sort(key=lambda item: item["searched_at"], reverse=True)
        return {
            "selected_history_id": selected_history_id or "",
            "items": items,
        }

    def _focus_route_history(self, history_id):
        if not history_id or self.route_history_layer is None:
            return

        route_feature = self._route_feature_for_history(history_id)
        if route_feature is None:
            return

        self.route_history_layer.removeSelection()
        self.route_history_layer.selectByIds([route_feature.id()])

        guide_features = self._guidance_features_for_history(history_id)
        if self.guidance_history_layer is not None:
            self.guidance_history_layer.removeSelection()
            self.guidance_history_layer.selectByIds(
                [feature.id() for feature in guide_features]
            )

        guidance_payload = self._route_guidance_payload_from_history(
            route_feature,
            guide_features,
        )
        points = self._route_points_from_geometry(route_feature.geometry())
        if len(points) >= 2:
            vehicle_options = guidance_payload["summary"]["vehicle"]
            avoid_options = guidance_payload["summary"]["avoid"]
            self._create_route_layer(
                points,
                self._safe_number(route_feature["distance_m"]),
                self._safe_number(route_feature["duration_s"]),
                self._safe_number(route_feature["guidance_count"]),
                str(route_feature["result_summary"] or ""),
                str(route_feature["priority"] or ""),
                self._waypoint_count_from_history(route_feature),
                avoid_options,
                vehicle_options,
            )
        else:
            self._zoom_to_geometry(route_feature.geometry())
        self._create_route_guidance_layer(guidance_payload["guides"])

        center = route_feature.geometry().centroid().asPoint()
        if self.dock is not None:
            self.dock.set_center(center.x(), center.y())
            self.dock.set_route_guidance(guidance_payload)
        self._sync_route_history_panel(history_id)
        self.iface.messageBar().pushInfo(
            "Kakao QGIS Bridge",
            f"경로 이력 선택: {route_feature['result_summary']}",
        )

    def _load_route_history(self, history_id):
        route_feature = self._route_feature_for_history(history_id)
        if route_feature is None or self.dock is None:
            return

        payload = self._route_input_payload_from_history(route_feature)
        script = "window.loadRouteHistoryInput({payload});".format(
            payload=json.dumps(payload, ensure_ascii=False)
        )
        self.dock.web_view.page().runJavaScript(script)
        self.iface.messageBar().pushInfo(
            "Kakao QGIS Bridge",
            "선택한 이력을 경로 입력창으로 불러왔습니다.",
        )

    def _delete_route_history(self, history_id):
        route_feature = self._route_feature_for_history(history_id)
        if route_feature is None:
            return

        answer = QMessageBox.question(
            self.iface.mainWindow(),
            "Kakao QGIS Bridge",
            (
                "선택한 경로 이력을 삭제할까요?\n\n"
                f"{route_feature['origin_name']} → "
                f"{route_feature['destination_name']}"
            ),
            MSGBOX_YES | MSGBOX_NO,
            MSGBOX_NO,
        )
        if answer != MSGBOX_YES:
            return

        if self.route_history_layer is not None:
            self.route_history_layer.dataProvider().deleteFeatures(
                [route_feature.id()]
            )
            self.route_history_layer.updateExtents()

        if self.guidance_history_layer is not None:
            guidance_ids = [
                feature.id()
                for feature in self._guidance_features_for_history(history_id)
            ]
            if guidance_ids:
                self.guidance_history_layer.dataProvider().deleteFeatures(
                    guidance_ids
                )
                self.guidance_history_layer.updateExtents()

        self._sync_route_history_panel()
        self._update_history_action_state()
        self.iface.messageBar().pushInfo(
            "Kakao QGIS Bridge",
            "선택한 경로 이력을 삭제했습니다.",
        )

    def _export_single_route_history(self, history_id):
        route_feature = self._route_feature_for_history(history_id)
        if route_feature is None:
            return

        formats = [
            "GeoPackage (*.gpkg)",
            "GeoJSON (*.geojson)",
            "Shapefile (*.shp)",
            "GPX (*.gpx)",
        ]
        selected_format, accepted = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Kakao QGIS Bridge",
            "선택한 경로 이력을 내보낼 형식",
            formats,
            0,
            False,
        )
        if not accepted:
            return

        base_name = self._history_export_basename(route_feature)
        project_home = QgsProject.instance().homePath()
        extension = {
            formats[0]: ".gpkg",
            formats[1]: ".geojson",
            formats[2]: ".shp",
            formats[3]: ".gpx",
        }[selected_format]
        default_name = f"{base_name}{extension}"
        default_path = (
            str(Path(project_home) / default_name)
            if project_home
            else default_name
        )
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "선택 경로 이력 내보내기",
            default_path,
            selected_format,
        )
        if not filename:
            return

        route_layer = self._single_history_layer(
            self.route_history_layer,
            [route_feature],
            "LineString",
            "Selected Kakao Route History",
        )
        guidance_features = self._guidance_features_for_history(history_id)
        guidance_layer = self._single_history_layer(
            self.guidance_history_layer,
            guidance_features,
            "Point",
            "Selected Kakao Guidance History",
        )

        try:
            if selected_format == formats[0]:
                output_path = Path(filename)
                if output_path.suffix.lower() != ".gpkg":
                    output_path = output_path.with_suffix(".gpkg")
                route_count = self._write_history_layer(
                    route_layer,
                    output_path,
                    ROUTE_HISTORY_LAYER_NAME,
                    "LineString",
                )
                guidance_count = self._write_history_layer(
                    guidance_layer,
                    output_path,
                    GUIDANCE_HISTORY_LAYER_NAME,
                    "Point",
                )
                output_parent = output_path.parent
            elif selected_format == formats[1]:
                route_path, guidance_path = self._geojson_output_paths(filename)
                route_count = self._write_geojson_history_layer(
                    route_layer,
                    route_path,
                    "Kakao Route History",
                )
                guidance_count = self._write_geojson_history_layer(
                    guidance_layer,
                    guidance_path,
                    "Kakao Guidance History",
                )
                output_parent = route_path.parent
            elif selected_format == formats[2]:
                route_path, guidance_path = self._paired_output_paths(
                    filename,
                    ".shp",
                )
                route_count = self._write_shapefile_history_layer(
                    route_layer,
                    route_path,
                    "LineString",
                    "Kakao Route History",
                    self._route_shapefile_fields(),
                )
                guidance_count = self._write_shapefile_history_layer(
                    guidance_layer,
                    guidance_path,
                    "Point",
                    "Kakao Guidance History",
                    self._guidance_shapefile_fields(),
                )
                output_parent = route_path.parent
            else:
                output_path = Path(filename)
                if output_path.suffix.lower() != ".gpx":
                    output_path = output_path.with_suffix(".gpx")
                route_count, guidance_count = self._write_gpx_history(
                    route_layer,
                    guidance_layer,
                    output_path,
                )
                output_parent = output_path.parent
        except RuntimeError as exc:
            QgsMessageLog.logMessage(
                str(exc),
                LOG_TAG,
                MSG_CRITICAL,
            )
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                f"선택 경로 이력 내보내기에 실패했습니다.\n\n{exc}",
            )
            return

        self.iface.messageBar().pushSuccess(
            "Kakao QGIS Bridge",
            (
                f"선택 이력 내보내기 완료: 경로 {route_count}건, "
                f"안내 {guidance_count}건 ({output_parent})"
            ),
        )

    def _update_history_action_state(self):
        has_history = (
            self.route_history_layer is not None
            and self.route_history_layer.featureCount() > 0
        )
        if self.save_history_action is not None:
            self.save_history_action.setEnabled(has_history)
        if self.export_geojson_action is not None:
            self.export_geojson_action.setEnabled(has_history)
        if self.export_shapefile_action is not None:
            self.export_shapefile_action.setEnabled(has_history)
        if self.export_gpx_action is not None:
            self.export_gpx_action.setEnabled(has_history)

    def _route_feature_for_history(self, history_id):
        if self.route_history_layer is None:
            return None
        for feature in self.route_history_layer.getFeatures():
            if str(feature["history_id"]) == history_id:
                return QgsFeature(feature)
        return None

    def _guidance_features_for_history(self, history_id):
        if self.guidance_history_layer is None:
            return []
        features = [
            feature
            for feature in self.guidance_history_layer.getFeatures()
            if str(feature["history_id"]) == history_id
        ]
        features.sort(key=lambda feature: self._safe_number(feature["sequence"]))
        return [QgsFeature(feature) for feature in features]

    def _route_input_payload_from_history(self, route_feature):
        waypoints = []
        try:
            parsed = json.loads(str(route_feature["waypoints_json"] or "[]"))
            if isinstance(parsed, list):
                waypoints = parsed[:MAX_ROUTE_WAYPOINTS]
        except (TypeError, ValueError, json.JSONDecodeError):
            waypoints = []

        return {
            "origin": {
                "label": str(route_feature["origin_name"] or ""),
                "lon": self._safe_float(route_feature["origin_lon"]),
                "lat": self._safe_float(route_feature["origin_lat"]),
            },
            "destination": {
                "label": str(route_feature["destination_name"] or ""),
                "lon": self._safe_float(route_feature["destination_lon"]),
                "lat": self._safe_float(route_feature["destination_lat"]),
            },
            "waypoints": [
                {
                    "label": str(item.get("label") or ""),
                    "lon": self._safe_float(item.get("lon")),
                    "lat": self._safe_float(item.get("lat")),
                }
                for item in waypoints
                if isinstance(item, dict)
            ],
            "priority": str(route_feature["priority"] or "RECOMMEND"),
            "avoid": [
                value
                for value in str(route_feature["avoid"] or "").split("|")
                if value
            ],
            "vehicle": {
                "car_type": self._safe_number(route_feature["car_type"]) or 1,
                "car_fuel": str(route_feature["car_fuel"] or "GASOLINE"),
                "car_hipass": bool(self._safe_number(route_feature["car_hipass"])),
            },
        }

    @staticmethod
    def _single_history_layer(source_layer, features, geometry_name, layer_name):
        layer = QgsVectorLayer(
            f"{geometry_name}?crs={source_layer.crs().authid()}",
            layer_name,
            "memory",
        )
        provider = layer.dataProvider()
        provider.addAttributes(list(source_layer.fields()))
        layer.updateFields()
        copied_features = []
        for source_feature in features:
            feature = QgsFeature(layer.fields())
            feature.setGeometry(source_feature.geometry())
            feature.setAttributes(source_feature.attributes())
            copied_features.append(feature)
        if copied_features:
            provider.addFeatures(copied_features)
            layer.updateExtents()
        layer.setRenderer(source_layer.renderer().clone())
        return layer

    @staticmethod
    def _history_export_basename(route_feature):
        searched = str(route_feature["searched_at"] or "")
        date_part = searched[:10].replace("-", "") or datetime.now().strftime("%Y%m%d")
        origin = str(route_feature["origin_name"] or "origin").strip()
        destination = str(route_feature["destination_name"] or "destination").strip()
        raw_name = f"kakao_route_{date_part}_{origin}_to_{destination}"
        safe = "".join(
            character if character.isalnum() or character in ("-", "_") else "_"
            for character in raw_name
        )
        while "__" in safe:
            safe = safe.replace("__", "_")
        return safe[:120].strip("_") or f"kakao_route_{date_part}"

    def _route_guidance_payload_from_history(self, route_feature, guide_features):
        vehicle = {
            "car_type": self._safe_number(route_feature["car_type"]),
            "car_fuel": str(route_feature["car_fuel"] or ""),
            "car_hipass": bool(self._safe_number(route_feature["car_hipass"])),
        }
        avoid = [
            value
            for value in str(route_feature["avoid"] or "").split("|")
            if value
        ]
        return {
            "route_id": str(route_feature["route_id"] or ""),
            "summary": {
                "distance_m": self._safe_number(route_feature["distance_m"]),
                "duration_s": self._safe_number(route_feature["duration_s"]),
                "guidance_count": self._safe_number(
                    route_feature["guidance_count"]
                ),
                "result_summary": str(route_feature["result_summary"] or ""),
                "priority": str(route_feature["priority"] or ""),
                "avoid": avoid,
                "vehicle": vehicle,
            },
            "guides": [
                {
                    "route_id": str(feature["route_id"] or ""),
                    "sequence": self._safe_number(feature["sequence"]),
                    "section_no": self._safe_number(feature["section_no"]),
                    "guide_type": self._safe_number(feature["guide_type"]),
                    "category": str(feature["category"] or "other"),
                    "guidance": str(feature["guidance"] or "경로 안내"),
                    "name": str(feature["name"] or ""),
                    "distance_m": self._safe_number(feature["distance_m"]),
                    "duration_s": self._safe_number(feature["duration_s"]),
                    "cumulative_distance_m": self._safe_number(
                        feature["cum_distance_m"]
                    ),
                    "cumulative_duration_s": self._safe_number(
                        feature["cum_duration_s"]
                    ),
                    "road_index": self._safe_number(feature["road_index"]),
                    "longitude": self._safe_float(feature["longitude"]),
                    "latitude": self._safe_float(feature["latitude"]),
                }
                for feature in guide_features
            ],
        }

    @staticmethod
    def _route_points_from_geometry(geometry):
        if geometry is None or geometry.isEmpty():
            return []
        if geometry.isMultipart():
            parts = geometry.asMultiPolyline()
            return parts[0] if parts else []
        return geometry.asPolyline()

    @staticmethod
    def _waypoint_count_from_history(route_feature):
        try:
            waypoints = json.loads(str(route_feature["waypoints_json"] or "[]"))
            return len(waypoints) if isinstance(waypoints, list) else 0
        except (TypeError, ValueError, json.JSONDecodeError):
            return 0

    def _zoom_to_geometry(self, geometry):
        if geometry is None or geometry.isEmpty():
            return

        canvas = self.iface.mapCanvas()
        project = QgsProject.instance()
        try:
            transform = QgsCoordinateTransform(
                QgsCoordinateReferenceSystem("EPSG:4326"),
                canvas.mapSettings().destinationCrs(),
                project,
            )
            extent = transform.transformBoundingBox(geometry.boundingBox())
            margin = max(extent.width(), extent.height()) * 0.08
            if margin > 0:
                extent.grow(margin)
            canvas.setExtent(extent)
            canvas.refresh()
        except Exception as exc:
            QgsMessageLog.logMessage(str(exc), LOG_TAG, MSG_WARNING)

    def _zoom_to_layers(self, layers):
        canvas = self.iface.mapCanvas()
        project = QgsProject.instance()
        combined_extent = None

        for layer in layers:
            if layer is None or not layer.isValid() or layer.featureCount() == 0:
                continue
            try:
                transform = QgsCoordinateTransform(
                    layer.crs(),
                    canvas.mapSettings().destinationCrs(),
                    project,
                )
                extent = transform.transformBoundingBox(layer.extent())
            except Exception as exc:
                QgsMessageLog.logMessage(
                    str(exc),
                    LOG_TAG,
                    MSG_WARNING,
                )
                continue

            if combined_extent is None:
                combined_extent = extent
            else:
                combined_extent.combineExtentWith(extent)

        if combined_extent is None:
            return

        margin = max(combined_extent.width(), combined_extent.height()) * 0.08
        if margin > 0:
            combined_extent.grow(margin)
        canvas.setExtent(combined_extent)
        canvas.refresh()

    @staticmethod
    def _safe_number(value):
        try:
            if value is None:
                return 0
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _safe_float(value):
        try:
            if value is None:
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _save_route_history_geopackage(self, _checked=False):
        if (
            self.route_history_layer is None
            or self.route_history_layer.featureCount() == 0
        ):
            QMessageBox.information(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                "저장할 경로 검색 이력이 없습니다. 경로를 먼저 생성해 주세요.",
            )
            return

        project_home = QgsProject.instance().homePath()
        default_name = f"kakao_route_history_{datetime.now():%Y%m%d}.gpkg"
        default_path = (
            str(Path(project_home) / default_name)
            if project_home
            else default_name
        )
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "경로 이력 GeoPackage 저장",
            default_path,
            "GeoPackage (*.gpkg)",
        )
        if not filename:
            return

        output_path = Path(filename)
        if output_path.suffix.lower() != ".gpkg":
            output_path = output_path.with_suffix(".gpkg")

        try:
            route_count = self._write_history_layer(
                self.route_history_layer,
                output_path,
                ROUTE_HISTORY_LAYER_NAME,
                "LineString",
            )
            guidance_count = self._write_history_layer(
                self.guidance_history_layer,
                output_path,
                GUIDANCE_HISTORY_LAYER_NAME,
                "Point",
            )
        except RuntimeError as exc:
            QgsMessageLog.logMessage(
                str(exc),
                LOG_TAG,
                MSG_CRITICAL,
            )
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                f"GeoPackage 저장에 실패했습니다.\n\n{exc}",
            )
            return

        if route_count == 0 and guidance_count == 0:
            message = "선택한 GeoPackage에 현재 세션 이력이 이미 저장되어 있습니다."
        else:
            message = (
                f"GeoPackage 저장 완료: 경로 {route_count}건, "
                f"안내 {guidance_count}건"
            )
        message = f"{message} ({output_path})"
        self.iface.messageBar().pushSuccess("Kakao QGIS Bridge", message)

    def _export_route_history_geojson(self, _checked=False):
        if (
            self.route_history_layer is None
            or self.route_history_layer.featureCount() == 0
        ):
            QMessageBox.information(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                "내보낼 경로 검색 이력이 없습니다. 경로를 먼저 생성해 주세요.",
            )
            return

        project_home = QgsProject.instance().homePath()
        default_name = f"kakao_route_history_{datetime.now():%Y%m%d}.geojson"
        default_path = (
            str(Path(project_home) / default_name)
            if project_home
            else default_name
        )
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "경로·안내 이력 GeoJSON 내보내기",
            default_path,
            "GeoJSON (*.geojson)",
        )
        if not filename:
            return

        route_path, guidance_path = self._geojson_output_paths(filename)
        output_paths = [
            route_path,
            guidance_path,
            route_path.with_suffix(".qml"),
            guidance_path.with_suffix(".qml"),
        ]
        existing_paths = [path for path in output_paths if path.exists()]
        if existing_paths:
            filenames = "\n".join(path.name for path in existing_paths)
            answer = QMessageBox.question(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                "다음 파일을 덮어쓸까요?\n\n" + filenames,
                MSGBOX_YES
                | MSGBOX_NO,
                MSGBOX_NO,
            )
            if answer != MSGBOX_YES:
                return

        try:
            route_count = self._write_geojson_history_layer(
                self.route_history_layer,
                route_path,
                "Kakao Route History",
            )
            guidance_count = self._write_geojson_history_layer(
                self.guidance_history_layer,
                guidance_path,
                "Kakao Guidance History",
            )
        except RuntimeError as exc:
            QgsMessageLog.logMessage(
                str(exc),
                LOG_TAG,
                MSG_CRITICAL,
            )
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                f"GeoJSON 내보내기에 실패했습니다.\n\n{exc}",
            )
            return

        message = (
            f"GeoJSON 내보내기 완료: 경로 {route_count}건, "
            f"안내 {guidance_count}건 ({route_path.parent})"
        )
        self.iface.messageBar().pushSuccess("Kakao QGIS Bridge", message)

    def _export_route_history_shapefile(self, _checked=False):
        if (
            self.route_history_layer is None
            or self.route_history_layer.featureCount() == 0
        ):
            QMessageBox.information(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                "내보낼 경로 검색 이력이 없습니다. 경로를 먼저 생성해 주세요.",
            )
            return

        project_home = QgsProject.instance().homePath()
        default_name = f"kakao_route_history_{datetime.now():%Y%m%d}.shp"
        default_path = (
            str(Path(project_home) / default_name)
            if project_home
            else default_name
        )
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "경로·안내 이력 Shapefile 내보내기",
            default_path,
            "Shapefile (*.shp)",
        )
        if not filename:
            return

        route_path, guidance_path = self._paired_output_paths(
            filename,
            ".shp",
        )
        output_paths = self._shapefile_sidecar_paths(route_path)
        output_paths.extend(self._shapefile_sidecar_paths(guidance_path))
        existing_paths = [path for path in output_paths if path.exists()]
        if existing_paths:
            filenames = "\n".join(path.name for path in existing_paths)
            answer = QMessageBox.question(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                "다음 파일을 덮어쓸까요?\n\n" + filenames,
                MSGBOX_YES
                | MSGBOX_NO,
                MSGBOX_NO,
            )
            if answer != MSGBOX_YES:
                return

        try:
            route_count = self._write_shapefile_history_layer(
                self.route_history_layer,
                route_path,
                "LineString",
                "Kakao Route History",
                self._route_shapefile_fields(),
            )
            guidance_count = self._write_shapefile_history_layer(
                self.guidance_history_layer,
                guidance_path,
                "Point",
                "Kakao Guidance History",
                self._guidance_shapefile_fields(),
            )
        except RuntimeError as exc:
            QgsMessageLog.logMessage(
                str(exc),
                LOG_TAG,
                MSG_CRITICAL,
            )
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                f"Shapefile 내보내기에 실패했습니다.\n\n{exc}",
            )
            return

        message = (
            f"Shapefile 내보내기 완료: 경로 {route_count}건, "
            f"안내 {guidance_count}건 ({route_path.parent})"
        )
        self.iface.messageBar().pushSuccess("Kakao QGIS Bridge", message)

    def _export_route_history_gpx(self, _checked=False):
        if (
            self.route_history_layer is None
            or self.route_history_layer.featureCount() == 0
        ):
            QMessageBox.information(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                "내보낼 경로 검색 이력이 없습니다. 경로를 먼저 생성해 주세요.",
            )
            return

        project_home = QgsProject.instance().homePath()
        default_name = f"kakao_route_history_{datetime.now():%Y%m%d}.gpx"
        default_path = (
            str(Path(project_home) / default_name)
            if project_home
            else default_name
        )
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "경로·안내 이력 GPX 내보내기",
            default_path,
            "GPX (*.gpx)",
        )
        if not filename:
            return

        output_path = Path(filename)
        if output_path.suffix.lower() != ".gpx":
            output_path = output_path.with_suffix(".gpx")
        if output_path.exists():
            answer = QMessageBox.question(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                f"{output_path.name} 파일을 덮어쓸까요?",
                MSGBOX_YES
                | MSGBOX_NO,
                MSGBOX_NO,
            )
            if answer != MSGBOX_YES:
                return

        try:
            route_count, guidance_count = self._write_gpx_history(
                self.route_history_layer,
                self.guidance_history_layer,
                output_path,
            )
        except RuntimeError as exc:
            QgsMessageLog.logMessage(
                str(exc),
                LOG_TAG,
                MSG_CRITICAL,
            )
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Kakao QGIS Bridge",
                f"GPX 내보내기에 실패했습니다.\n\n{exc}",
            )
            return

        message = (
            f"GPX 내보내기 완료: 경로 {route_count}건, "
            f"안내 {guidance_count}건 ({output_path.parent})"
        )
        self.iface.messageBar().pushSuccess("Kakao QGIS Bridge", message)

    @staticmethod
    def _geojson_output_paths(filename):
        return KakaoQgisBridgePlugin._paired_output_paths(filename, ".geojson")

    @staticmethod
    def _paired_output_paths(filename, extension):
        selected_path = Path(filename)
        if selected_path.suffix.lower() != extension:
            selected_path = selected_path.with_suffix(extension)

        base_stem = selected_path.stem
        for paired_suffix in ("_routes", "_guidance"):
            if base_stem.lower().endswith(paired_suffix):
                base_stem = base_stem[:-len(paired_suffix)]
                break

        route_path = selected_path.with_name(
            f"{base_stem}_routes{selected_path.suffix}"
        )
        guidance_path = selected_path.with_name(
            f"{base_stem}_guidance{selected_path.suffix}"
        )
        return route_path, guidance_path

    def _write_geojson_history_layer(
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
            QgsProject.instance().transformContext(),
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

    def _write_shapefile_history_layer(
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
            QgsProject.instance().transformContext(),
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

    def _write_gpx_history(self, route_layer, guidance_layer, output_path):
        ET.register_namespace("", "http://www.topografix.com/GPX/1/1")
        ET.register_namespace("kakao", "https://yjkim.dev/kakao-qgis-bridge")
        root = ET.Element(
            "{http://www.topografix.com/GPX/1/1}gpx",
            {
                "version": "1.1",
                "creator": "Kakao QGIS Bridge",
            },
        )

        metadata = ET.SubElement(
            root,
            "{http://www.topografix.com/GPX/1/1}metadata",
        )
        self._gpx_text(metadata, "name", "Kakao QGIS Bridge Route History")
        self._gpx_text(
            metadata,
            "time",
            datetime.now().astimezone().isoformat(timespec="seconds"),
        )

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

            self._append_gpx_waypoints(root, route_feature, guides)
            self._append_gpx_track(root, name, desc, route_feature, points)
            self._append_gpx_route(root, name, desc, route_feature, points)

        tree = ET.ElementTree(root)
        try:
            tree.write(
                str(output_path),
                encoding="utf-8",
                xml_declaration=True,
                short_empty_elements=True,
            )
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
        tracks_layer.renderer().setSymbol(self._route_line_symbol())
        self._save_layer_style_to_path(
            tracks_layer,
            output_path.with_name(f"{output_path.stem}_tracks.qml"),
        )

        routes_layer = QgsVectorLayer(
            "LineString?crs=EPSG:4326&field=name:string(255)&field=type:string(32)",
            "Kakao GPX Routes",
            "memory",
        )
        routes_layer.renderer().setSymbol(self._route_line_symbol())
        self._save_layer_style_to_path(
            routes_layer,
            output_path.with_name(f"{output_path.stem}_routes.qml"),
        )

        waypoints_layer = QgsVectorLayer(
            "Point?crs=EPSG:4326&field=name:string(255)&field=type:string(64)",
            "Kakao GPX Waypoints",
            "memory",
        )
        waypoints_layer.setRenderer(self._gpx_waypoint_renderer())
        self._save_layer_style_to_path(
            waypoints_layer,
            output_path.with_name(f"{output_path.stem}_waypoints.qml"),
        )

    def _gpx_waypoint_renderer(self):
        return QgsCategorizedSymbolRenderer(
            "type",
            [
                QgsRendererCategory(
                    "origin",
                    self._route_pin_symbol("route_origin_pin.svg", 7.5),
                    "출발지",
                ),
                QgsRendererCategory(
                    "destination",
                    self._route_pin_symbol("route_destination_pin.svg", 7.5),
                    "도착지",
                ),
                QgsRendererCategory(
                    "waypoint",
                    self._route_pin_symbol("route_waypoint_pin.svg", 7.5),
                    "경유지",
                ),
                QgsRendererCategory(
                    "guidance:straight",
                    self._guidance_symbol("guidance_straight.svg"),
                    "직진",
                ),
                QgsRendererCategory(
                    "guidance:left",
                    self._guidance_symbol("guidance_left.svg"),
                    "좌회전",
                ),
                QgsRendererCategory(
                    "guidance:right",
                    self._guidance_symbol("guidance_right.svg"),
                    "우회전",
                ),
                QgsRendererCategory(
                    "guidance:uturn",
                    self._guidance_symbol("guidance_uturn.svg"),
                    "유턴",
                ),
                QgsRendererCategory(
                    "guidance:roundabout",
                    self._guidance_symbol("guidance_roundabout.svg"),
                    "회전교차로",
                ),
                QgsRendererCategory(
                    "guidance:transition",
                    self._guidance_symbol("guidance_transition.svg"),
                    "진출입",
                ),
                QgsRendererCategory(
                    "guidance:other",
                    self._guidance_symbol("guidance_other.svg"),
                    "기타 안내",
                ),
            ],
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
                key=lambda feature: KakaoQgisBridgePlugin._safe_number(
                    feature["sequence"]
                )
            )
        return grouped

    def _append_gpx_waypoints(self, root, route_feature, guide_features):
        history_id = str(route_feature["history_id"] or "")
        self._append_gpx_wpt(
            root,
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
                root,
                self._safe_float(waypoint.get("lon")),
                self._safe_float(waypoint.get("lat")),
                str(waypoint.get("label") or f"경유지 {index}"),
                "waypoint",
                history_id,
                f"경유지 {index}",
            )

        self._append_gpx_wpt(
            root,
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
                root,
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

    def _append_gpx_track(self, root, name, desc, route_feature, points):
        track = ET.SubElement(root, "{http://www.topografix.com/GPX/1/1}trk")
        self._gpx_text(track, "name", name)
        if desc:
            self._gpx_text(track, "desc", desc)
        self._append_gpx_extensions(track, route_feature)
        segment = ET.SubElement(
            track,
            "{http://www.topografix.com/GPX/1/1}trkseg",
        )
        for point in points:
            ET.SubElement(
                segment,
                "{http://www.topografix.com/GPX/1/1}trkpt",
                {
                    "lat": f"{point.y():.8f}",
                    "lon": f"{point.x():.8f}",
                },
            )

    def _append_gpx_route(self, root, name, desc, route_feature, points):
        route = ET.SubElement(root, "{http://www.topografix.com/GPX/1/1}rte")
        self._gpx_text(route, "name", name)
        if desc:
            self._gpx_text(route, "desc", desc)
        self._append_gpx_extensions(route, route_feature)
        for point in points:
            ET.SubElement(
                route,
                "{http://www.topografix.com/GPX/1/1}rtept",
                {
                    "lat": f"{point.y():.8f}",
                    "lon": f"{point.x():.8f}",
                },
            )

    def _append_gpx_wpt(
        self,
        root,
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

        waypoint = ET.SubElement(
            root,
            "{http://www.topografix.com/GPX/1/1}wpt",
            {
                "lat": f"{lat:.8f}",
                "lon": f"{lon:.8f}",
            },
        )
        self._gpx_text(waypoint, "name", name)
        if desc:
            self._gpx_text(waypoint, "desc", desc)
        self._gpx_text(waypoint, "type", point_type)

        extensions = ET.SubElement(
            waypoint,
            "{http://www.topografix.com/GPX/1/1}extensions",
        )
        self._gpx_kakao_text(extensions, "history_id", history_id)
        if extra:
            for key, value in extra.items():
                self._gpx_kakao_text(extensions, key, value)

    def _append_gpx_extensions(self, parent, route_feature):
        extensions = ET.SubElement(
            parent,
            "{http://www.topografix.com/GPX/1/1}extensions",
        )
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
            self._gpx_kakao_text(extensions, key, route_feature[key])

    @staticmethod
    def _gpx_text(parent, tag, value):
        element = ET.SubElement(
            parent,
            f"{{http://www.topografix.com/GPX/1/1}}{tag}",
        )
        element.text = str(value)
        return element

    @staticmethod
    def _gpx_kakao_text(parent, tag, value):
        element = ET.SubElement(
            parent,
            f"{{https://yjkim.dev/kakao-qgis-bridge}}{tag}",
        )
        element.text = str(value if value is not None else "")
        return element

    @staticmethod
    def _gpx_route_name(route_feature):
        origin = str(route_feature["origin_name"] or "출발지")
        destination = str(route_feature["destination_name"] or "도착지")
        return f"{origin} → {destination}"

    @staticmethod
    def _waypoints_from_history(route_feature):
        try:
            waypoints = json.loads(str(route_feature["waypoints_json"] or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        return waypoints if isinstance(waypoints, list) else []

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
                field_parts.append(f"&field={spec['name']}:double")
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
                if value is not None and spec["type"] == "string":
                    value = str(value)
                    max_length = spec["length"]
                    if len(value) > max_length:
                        value = value[:max_length]
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
        return [
            {"name": "schema_v", "source": "schema_ver", "type": "integer"},
            {"name": "hist_id", "source": "history_id", "type": "string", "length": 36},
            {"name": "route_id", "source": "route_id", "type": "string", "length": 64},
            {"name": "searched", "source": "searched_at", "type": "string", "length": 32},
            {"name": "org_lon", "source": "origin_lon", "type": "double"},
            {"name": "org_lat", "source": "origin_lat", "type": "double"},
            {"name": "org_name", "source": "origin_name", "type": "string", "length": 254},
            {"name": "dst_lon", "source": "destination_lon", "type": "double"},
            {"name": "dst_lat", "source": "destination_lat", "type": "double"},
            {"name": "dst_name", "source": "destination_name", "type": "string", "length": 254},
            {"name": "waypts", "source": "waypoints_json", "type": "string", "length": 254},
            {"name": "dist_m", "source": "distance_m", "type": "integer"},
            {"name": "dur_s", "source": "duration_s", "type": "integer"},
            {"name": "guide_cnt", "source": "guidance_count", "type": "integer"},
            {"name": "summary", "source": "result_summary", "type": "string", "length": 254},
            {"name": "priority", "source": "priority", "type": "string", "length": 16},
            {"name": "avoid", "source": "avoid", "type": "string", "length": 128},
            {"name": "car_type", "source": "car_type", "type": "integer"},
            {"name": "car_fuel", "source": "car_fuel", "type": "string", "length": 16},
            {"name": "car_hipass", "source": "car_hipass", "type": "integer"},
        ]

    @staticmethod
    def _guidance_shapefile_fields():
        return [
            {"name": "schema_v", "source": "schema_ver", "type": "integer"},
            {"name": "hist_id", "source": "history_id", "type": "string", "length": 36},
            {"name": "route_id", "source": "route_id", "type": "string", "length": 64},
            {"name": "searched", "source": "searched_at", "type": "string", "length": 32},
            {"name": "seq", "source": "sequence", "type": "integer"},
            {"name": "sect_no", "source": "section_no", "type": "integer"},
            {"name": "g_type", "source": "guide_type", "type": "integer"},
            {"name": "category", "source": "category", "type": "string", "length": 16},
            {"name": "guidance", "source": "guidance", "type": "string", "length": 254},
            {"name": "name", "source": "name", "type": "string", "length": 128},
            {"name": "dist_m", "source": "distance_m", "type": "integer"},
            {"name": "dur_s", "source": "duration_s", "type": "integer"},
            {"name": "cum_dist", "source": "cum_distance_m", "type": "integer"},
            {"name": "cum_dur", "source": "cum_duration_s", "type": "integer"},
            {"name": "road_idx", "source": "road_index", "type": "integer"},
            {"name": "lon", "source": "longitude", "type": "double"},
            {"name": "lat", "source": "latitude", "type": "double"},
        ]

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

    def _write_history_layer(
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
            QgsProject.instance().transformContext(),
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

    @staticmethod
    def _route_result_summary(
        distance,
        duration,
        car_type,
        guidance_count,
    ):
        duration_minutes = max(1, round(duration / 60))
        distance_km = distance / 1000
        car_label = ROUTE_CAR_TYPES.get(car_type, str(car_type))
        return (
            f"{duration_minutes}분 · {distance_km:.1f} km · "
            f"{car_label} · 안내 {guidance_count}개"
        )

    def _create_route_layer(
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
        self._remove_route_layer()

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
        layer.renderer().setSymbol(self._route_line_symbol())

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
            QgsMessageLog.logMessage(str(exc), LOG_TAG, MSG_WARNING)
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
        layer.setRenderer(self._route_guidance_renderer())

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
    def _route_line_symbol():
        return QgsLineSymbol.createSimple(
            {
                "line_color": "#1976d2",
                "line_width": "1.4",
            }
        )

    def _route_guidance_renderer(self):
        return QgsCategorizedSymbolRenderer(
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

    @staticmethod
    def _guidance_symbol(filename):
        return QgsMarkerSymbol(
            [
                QgsSvgMarkerSymbolLayer(
                    KakaoQgisBridgePlugin._embedded_svg_path(filename),
                    6.5,
                )
            ]
        )

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
        symbol_layer = QgsSvgMarkerSymbolLayer(
            KakaoQgisBridgePlugin._embedded_svg_path(filename),
            size,
        )
        symbol_layer.setVerticalAnchorPoint(Qgis.VerticalAnchorPoint.Bottom)
        return QgsMarkerSymbol([symbol_layer])

    @staticmethod
    @lru_cache(maxsize=None)
    def _embedded_svg_path(filename):
        svg_path = PLUGIN_DIR / "web" / filename
        encoded = b64encode(svg_path.read_bytes()).decode("ascii")
        return f"base64:{encoded}"

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
