import json
import math
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsMessageLog,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QTimer, Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices, QIcon
from qgis.PyQt.QtWidgets import QFileDialog, QInputDialog, QLineEdit, QMessageBox

try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction

from .compat import (
    MSGBOX_NO,
    MSGBOX_YES,
    MSG_CRITICAL,
    MSG_INFO,
    MSG_WARNING,
)
from .dock_widget import KakaoMapDockWidget
from .external_bridge import KakaoExternalBridgeServer
from .history_export_service import HistoryExportService
from . import history_values
from .history_repository import HistoryRepository
from .history_operations import HistoryOperationError
from .history_import_service import HistoryImportService
from .history_ui_controller import HistoryUiCallbacks, HistoryUiController
from .history_export_controller import HistoryExportCallbacks, HistoryExportController
from .style_factory import StyleFactory
from .display_layers import DisplayLayerManager
from .history_formats import (
    ROUTE_HISTORY_LAYER_NAME, GUIDANCE_HISTORY_LAYER_NAME,
)
from .mobility import (
    ROUTE_AVOID_OPTIONS,
    ROUTE_CAR_FUELS,
    ROUTE_CAR_TYPES,
    ROUTE_PRIORITIES,
    MAX_ROUTE_WAYPOINTS,
    RouteValidationError,
    normalize_route_request,
    route_result_summary,
)
from .mobility_client import MobilityClient
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
from .sync_controller import CanvasSyncController


MENU_NAME = "&Kakao QGIS Bridge"
LOG_TAG = "Kakao QGIS Bridge"
# An internal origin cannot collide with an external browser's client ID.
_DOCK_SYNC_SOURCE = object()


class KakaoQgisBridgePlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.external_viewer_action = None
        self.settings_action = None
        self.rest_settings_action = None
        self.load_history_action = None
        self.compare_routes_action = None
        self.comparison_dialog = None
        self.load_gpx_action = None
        self.save_history_action = None
        self.export_geojson_action = None
        self.export_shapefile_action = None
        self.export_gpx_action = None
        self.dock = None
        self.style_factory = StyleFactory()
        self.display_layers = DisplayLayerManager(QgsProject.instance(), self.style_factory)
        self.history_repository = HistoryRepository(
            self.style_factory.route_line_symbol,
            self.style_factory.route_guidance_renderer,
        )
        self.history_import_service = HistoryImportService(self.history_repository)
        self.history_export_ui = HistoryExportController(
            self.history_repository,
            HistoryExportCallbacks(
                current_epoch=lambda: self._project_epoch,
                current_iface=lambda: self.iface,
                write_geopackage=lambda *args: self._write_history_layer(*args),
                write_geojson=lambda *args: self._write_geojson_history_layer(*args),
                write_shapefile=lambda *args: self._write_shapefile_history_layer(*args),
                write_gpx=lambda *args: self._write_gpx_history(*args),
            ),
        )
        self.history_ui = HistoryUiController(
            self.iface,
            self.history_repository,
            HistoryUiCallbacks(
                current_epoch=lambda: self._project_epoch,
                active_history=lambda: self.active_route_history_id,
                show_history=self._show_route_history,
                load_input=self._send_route_history_input,
                clear_display=self._clear_current_route_display,
                publish_history=self._sync_route_history_panel,
                update_actions=self._update_history_action_state,
                handle_error=self._handle_history_operation_error,
            ),
        )
        self.active_route_history_id = None
        self._current_guidance_payload = {
            "history_id": "", "route_id": "", "summary": {}, "path": [], "guides": [],
        }
        self._last_route_status = None
        self.mobility_client = MobilityClient()
        self._project_epoch = 0
        self._project_transitioning = False
        self._project_signals_connected = False
        self._active_route_request = None
        self._route_request_epoch = None
        self.mobility_client.succeeded.connect(self._receive_route_result)
        self.mobility_client.failed.connect(self._receive_route_failure)
        self.sync_controller = CanvasSyncController(
            self.iface,
            self._has_canvas_sync_target,
        )
        self.sync_controller.syncRequested.connect(self._sync_canvas_center)
        self.external_bridge_server = None
        self._processing_external_bridge_events = False
        self.external_bridge_timer = QTimer()
        self.external_bridge_timer.setInterval(120)
        self.external_bridge_timer.timeout.connect(
            self._process_external_bridge_events
        )


    @property
    def roadview_layer(self):
        return self.display_layers.roadview_layer

    @roadview_layer.setter
    def roadview_layer(self, value):
        self.display_layers.roadview_layer = value

    @property
    def roadview_feature_id(self):
        return self.display_layers.roadview_feature_id

    @roadview_feature_id.setter
    def roadview_feature_id(self, value):
        self.display_layers.roadview_feature_id = value

    @property
    def route_layer(self):
        return self.display_layers.route_layer

    @route_layer.setter
    def route_layer(self, value):
        self.display_layers.route_layer = value

    @property
    def route_guidance_layer(self):
        return self.display_layers.route_guidance_layer

    @route_guidance_layer.setter
    def route_guidance_layer(self, value):
        self.display_layers.route_guidance_layer = value

    @property
    def route_guidance_feature_ids(self):
        return self.display_layers.route_guidance_feature_ids

    @route_guidance_feature_ids.setter
    def route_guidance_feature_ids(self, value):
        self.display_layers.route_guidance_feature_ids = value

    @property
    def route_points_layer(self):
        return self.display_layers.route_points_layer

    @route_points_layer.setter
    def route_points_layer(self, value):
        self.display_layers.route_points_layer = value

    @property
    def route_point_feature_ids(self):
        return self.display_layers.route_point_feature_ids

    @route_point_feature_ids.setter
    def route_point_feature_ids(self, value):
        self.display_layers.route_point_feature_ids = value

    @property
    def _route_point_categories(self):
        return self.display_layers.route_point_categories

    @_route_point_categories.setter
    def _route_point_categories(self, value):
        self.display_layers.route_point_categories = value

    @property
    def route_history_layer(self):
        return self.history_repository.route_layer

    @route_history_layer.setter
    def route_history_layer(self, layer):
        self.history_repository.route_layer = layer

    @property
    def guidance_history_layer(self):
        return self.history_repository.guidance_layer

    @guidance_history_layer.setter
    def guidance_history_layer(self, layer):
        self.history_repository.guidance_layer = layer

    def initGui(self):
        if not self._project_signals_connected:
            project = QgsProject.instance()
            project.aboutToBeCleared.connect(self._begin_project_transition)
            project.cleared.connect(self._finish_project_transition)
            self._project_signals_connected = True
        self.action = QAction(
            QIcon(str(PLUGIN_DIR / "icon.png")),
            "Kakao Map / Roadview",
            self.iface.mainWindow(),
        )
        self.action.setCheckable(True)
        self.action.triggered.connect(self.toggle_dock)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(MENU_NAME, self.action)

        self.external_viewer_action = QAction(
            QIcon.fromTheme("applications-internet"),
            "외부 브라우저 연동 창 열기...",
            self.iface.mainWindow(),
        )
        self.external_viewer_action.triggered.connect(self._open_external_viewer)
        self.iface.addPluginToMenu(MENU_NAME, self.external_viewer_action)

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

        self.compare_routes_action = QAction("GPKG 경로 비교...", self.iface.mainWindow())
        self.compare_routes_action.triggered.connect(self._open_route_comparison)
        self.iface.addPluginToMenu(MENU_NAME, self.compare_routes_action)

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
        if self.comparison_dialog is not None:
            self.comparison_dialog.dispose()
            self.comparison_dialog = None
        if self.compare_routes_action is not None:
            self.iface.removePluginMenu(MENU_NAME, self.compare_routes_action)
            self.compare_routes_action = None
        if self._project_signals_connected:
            project = QgsProject.instance()
            project.aboutToBeCleared.disconnect(self._begin_project_transition)
            project.cleared.disconnect(self._finish_project_transition)
            self._project_signals_connected = False
        self._active_route_request = None
        self._route_request_epoch = None
        self._deactivate_canvas_sync()

        if self.action is not None:
            self.iface.removePluginMenu(MENU_NAME, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None

        if self.external_viewer_action is not None:
            self.iface.removePluginMenu(MENU_NAME, self.external_viewer_action)
            self.external_viewer_action = None

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

        self.mobility_client.cancel()

        self._stop_external_bridge()

        if self.dock is not None:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None

        self.display_layers.remove_all()
        self.history_repository.clear()

    def _open_route_comparison(self):
        from .route_comparison_dialog import RouteComparisonDialog
        if self.comparison_dialog is None:
            self.comparison_dialog = RouteComparisonDialog(self.iface)
        self.comparison_dialog.show()
        self.comparison_dialog.raise_()
        self.comparison_dialog.activateWindow()

    def _begin_project_transition(self):
        self._project_epoch += 1
        self._project_transitioning = True
        self._active_route_request = None
        self._route_request_epoch = None
        self.mobility_client.cancel()
        self.sync_controller.reset_pending()
        if self.external_bridge_server is not None:
            self.external_bridge_server.pause_events()

    def _finish_project_transition(self):
        self.display_layers.forget_all()
        self.active_route_history_id = None
        # The repository and its recovery block belong to the plugin session.
        for layer in (self.route_history_layer, self.guidance_history_layer):
            if layer is not None:
                layer.removeSelection()
        server = self.external_bridge_server
        if server is not None:
            server.reset_project_state()
        if self.dock is not None:
            self.dock.reset_project(self._project_epoch)
        if server is not None:
            server.emit_signal("projectReset", self._project_epoch)
        self._set_route_guidance({"history_id": "", "route_id": "", "summary": {},
                                  "path": [], "guides": []})
        self._sync_route_history_panel()
        self._set_route_status(False, "프로젝트가 변경되어 현재 경로와 이전 요청을 초기화했습니다.")
        self._project_transitioning = False
        if server is not None:
            server.resume_events()
        self.sync_controller.schedule()

    def _receive_route_result(self, result, route_request):
        if (self._project_transitioning or route_request is not self._active_route_request
                or self._route_request_epoch != self._project_epoch):
            return
        self._active_route_request = None
        self._route_request_epoch = None
        self._handle_route_result(result, route_request)

    def _receive_route_failure(self, message):
        if (self._project_transitioning or self._active_route_request is None
                or self._route_request_epoch != self._project_epoch):
            return
        self._active_route_request = None
        self._route_request_epoch = None
        self._handle_route_failure(message)

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

        try:
            save_rest_api_key(value)
        except RouteValidationError as exc:
            QMessageBox.warning(
                self.iface.mainWindow(), "Kakao QGIS Bridge", str(exc)
            )
            return False
        return True

    def _hide_dock(self):
        if self.dock is not None:
            self.dock.hide()
        if self.external_bridge_server is None:
            self._deactivate_canvas_sync()

    def _ensure_dock(self):
        if self.dock is not None:
            return

        self.dock = KakaoMapDockWidget(self.iface.mainWindow())
        self.dock.centerRequested.connect(self._handle_dock_viewer_moved)
        self.dock.roadviewStateChanged.connect(self._update_roadview_layer)
        self.dock.routeRequested.connect(self._request_route)
        self.dock.routePointChanged.connect(self._set_route_point)
        self.dock.routePointCleared.connect(self._clear_route_point)
        self.dock.routePointsCleared.connect(self._clear_route_points)
        self.dock.routeGuidanceSelected.connect(self._focus_route_guidance)
        self.dock.routeHistorySelected.connect(self._focus_route_history)
        self.dock.routeHistoryFileLoadRequested.connect(
            self._load_route_history_file
        )
        self.dock.routeHistoryLoadRequested.connect(self._load_route_history)
        self.dock.routeHistoryDeleteRequested.connect(self._delete_route_history)
        self.dock.routeHistoriesDeleteRequested.connect(
            self._delete_all_route_histories
        )
        self.dock.routeHistoryExportRequested.connect(self._export_single_route_history)
        self.dock.routeHistoriesExportRequested.connect(
            self._export_selected_route_histories
        )
        self.dock.routeHistoryRefreshRequested.connect(
            self._refresh_route_history_panel
        )
        self.dock.externalViewerRequested.connect(self._open_external_viewer)
        self.dock.visibilityChanged.connect(self._sync_action_state)
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        if self.dock.web_runtime_diagnostic:
            self._ensure_external_bridge()
            QgsMessageLog.logMessage(
                self.dock.web_runtime_diagnostic,
                LOG_TAG,
                MSG_WARNING,
            )
        QTimer.singleShot(800, self._sync_route_history_panel)

    def _ensure_external_bridge(self):
        if self.external_bridge_server is None:
            self.external_bridge_server = KakaoExternalBridgeServer(fallback_ports=(8082,))
            try:
                self.external_bridge_server.emit_signal(
                    "routeGuidanceChanged",
                    json.dumps(self._current_guidance_payload, ensure_ascii=False),
                )
                self.external_bridge_server.emit_signal(
                    "routeHistoryChanged",
                    json.dumps(self._route_history_payload(self.active_route_history_id), ensure_ascii=False),
                )
                if self._last_route_status is not None:
                    self.external_bridge_server.emit_signal("routeStatusChanged", *self._last_route_status)
                self.external_bridge_server.start()
            except OSError as exc:
                QgsMessageLog.logMessage(str(exc), LOG_TAG, MSG_WARNING)
                self.iface.messageBar().pushWarning(
                    "Kakao QGIS Bridge",
                    "외부 브라우저 연동 서버를 시작하지 못했습니다. "
                    "localhost:8081과 localhost:8082를 다른 프로그램이 사용 중인지 확인하세요. "
                    "사용 중인 외부 연동 서버를 종료한 뒤 다시 시도하세요.",
                )
                self.external_bridge_server = None
                return None

        if not self.external_bridge_timer.isActive():
            self.external_bridge_timer.start()
        self._sync_canvas_center()
        return self.external_bridge_server

    def _stop_external_bridge(self):
        self.external_bridge_timer.stop()
        if self.external_bridge_server is not None:
            self.external_bridge_server.stop()
            self.external_bridge_server = None
        if self.dock is None or not self.dock.isVisible():
            self._deactivate_canvas_sync()

    def _open_external_viewer(self):
        if not self._ensure_api_key():
            return

        server = self._ensure_external_bridge()
        if server is None:
            return

        self._activate_canvas_sync()
        self.iface.messageBar().pushInfo(
            "Kakao QGIS Bridge",
            f"외부 연동 주소: {server.origin} · "
            "Kakao Developers의 기존 JavaScript 키에 이 주소를 SDK 도메인으로 등록하세요. "
            "동시 사용 시 http://localhost:8081과 http://localhost:8082를 모두 등록하세요.",
        )
        QDesktopServices.openUrl(QUrl(server.url))

    def _process_external_bridge_events(self):
        server = self.external_bridge_server
        if server is None or self._processing_external_bridge_events or self._project_transitioning:
            return

        self._processing_external_bridge_events = True
        try:
            self._dispatch_external_bridge_events(server)
        finally:
            self._processing_external_bridge_events = False

    def _dispatch_external_bridge_events(self, server):
        epoch = self._project_epoch
        for event in server.drain_events():
            # A dialog can allow plugin shutdown before processing resumes.
            if self.external_bridge_server is not server or epoch != self._project_epoch:
                break
            event_type = None
            try:
                event_type = event.get("type")
                payload = event.get("payload", {})
                if not isinstance(payload, dict):
                    raise TypeError("외부 이벤트 payload는 객체여야 합니다.")
                if event_type == "move_center":
                    self._handle_viewer_moved(
                        float(payload.get("lon")),
                        float(payload.get("lat")),
                        source=event.get("source"),
                    )
                elif event_type == "roadview_state":
                    self._update_roadview_layer(
                        float(payload.get("lon")),
                        float(payload.get("lat")),
                        float(payload.get("pan")),
                        float(payload.get("tilt")),
                        float(payload.get("zoom")),
                        str(payload.get("pano_id", "")),
                    )
                elif event_type == "request_route":
                    self._request_route(
                        float(payload.get("origin_lon")),
                        float(payload.get("origin_lat")),
                        float(payload.get("destination_lon")),
                        float(payload.get("destination_lat")),
                        str(payload.get("priority", "")),
                        str(payload.get("waypoints_json", "")),
                        str(payload.get("avoid_json", "")),
                        str(payload.get("vehicle_json", "")),
                        str(payload.get("origin_label", "")),
                        str(payload.get("destination_label", "")),
                    )
                elif event_type == "route_point":
                    self._set_route_point(
                        str(payload.get("role", "")),
                        float(payload.get("lon")),
                        float(payload.get("lat")),
                    )
                elif event_type == "clear_route_point":
                    self._clear_route_point(str(payload.get("role", "")))
                elif event_type == "clear_route_points":
                    self._clear_route_points()
                elif event_type == "select_route_guidance":
                    self._focus_route_guidance(
                        int(payload.get("sequence")),
                        float(payload.get("lon")),
                        float(payload.get("lat")),
                    )
                elif event_type == "select_route_history":
                    self._focus_route_history(str(payload.get("history_id", "")))
                elif event_type == "load_route_history_file":
                    self._load_route_history_file()
                elif event_type == "load_route_history":
                    self._load_route_history(str(payload.get("history_id", "")))
                elif event_type == "delete_route_history":
                    self._delete_route_history(str(payload.get("history_id", "")))
                elif event_type == "delete_all_route_histories":
                    self._delete_all_route_histories()
                elif event_type == "export_route_history":
                    self._export_single_route_history(
                        str(payload.get("history_id", ""))
                    )
                elif event_type == "export_route_histories":
                    self._export_selected_route_histories(
                        str(payload.get("history_ids_json", "[]"))
                    )
                elif event_type == "refresh_route_history":
                    self._refresh_route_history_panel()
            except Exception as exc:
                QgsMessageLog.logMessage(
                    f"외부 이벤트 {event_type or '미상'} 처리 실패 "
                    f"({type(exc).__name__}): {exc}", LOG_TAG, MSG_WARNING,
                )
                if event_type == "request_route":
                    try:
                        self._set_route_status(
                            False,
                            "외부 브라우저의 경로 요청을 처리하지 못했습니다.",
                        )
                    except Exception as status_exc:
                        QgsMessageLog.logMessage(
                            f"경로 요청 실패 안내를 전달하지 못했습니다 "
                            f"({type(status_exc).__name__}): {status_exc}",
                            LOG_TAG, MSG_WARNING,
                        )

    def _sync_action_state(self, visible):
        if self.action is not None:
            self.action.setChecked(visible)

        if visible:
            self._activate_canvas_sync()
        elif self.external_bridge_server is None:
            self._deactivate_canvas_sync()

    def _activate_canvas_sync(self):
        if self.sync_controller.activate():
            if self.dock is not None and self.dock.web_view is None:
                self.iface.messageBar().pushInfo(
                    "Kakao QGIS Bridge",
                    "외부 브라우저 모드입니다. QGIS 중심 좌표를 기준으로 Kakao Map/Roadview를 열 수 있습니다.",
                )
            else:
                self.iface.messageBar().pushInfo(
                    "Kakao QGIS Bridge",
                    "QGIS 이동은 Kakao에, Roadview 위치 이동은 QGIS에 양방향으로 반영됩니다.",
                )

    def _deactivate_canvas_sync(self):
        self.sync_controller.deactivate()

    def _schedule_canvas_sync(self, *_args):
        self.sync_controller.schedule()

    def _sync_canvas_center(self, source=None):
        if self._project_transitioning:
            return
        if not self._has_canvas_sync_target():
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

        if source is not _DOCK_SYNC_SOURCE and self.dock is not None and self.dock.isVisible():
            self.dock.set_center(lon, lat)
        if self.external_bridge_server is not None:
            self.external_bridge_server.set_center(
                lon, lat, source=None if source is _DOCK_SYNC_SOURCE else source,
            )

    def _has_canvas_sync_target(self):
        dock_visible = self.dock is not None and self.dock.isVisible()
        return dock_visible or self.external_bridge_server is not None

    def _handle_dock_viewer_moved(self, lon, lat):
        self._handle_viewer_moved(lon, lat, source=_DOCK_SYNC_SOURCE)

    def _handle_viewer_moved(self, lon, lat, source=None):
        if self._project_transitioning:
            return
        if not math.isfinite(lon) or not math.isfinite(lat):
            return
        if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
            return

        canvas = self.iface.mapCanvas()
        try:
            center = self.sync_controller.from_wgs84(lon, lat)
        except Exception as exc:
            QgsMessageLog.logMessage(str(exc), LOG_TAG, MSG_WARNING)
            self.iface.messageBar().pushWarning(
                "Kakao QGIS Bridge",
                "Kakao 지도/Roadview 좌표를 QGIS 프로젝트 좌표계로 변환하지 못했습니다.",
            )
            return

        self.sync_controller.begin_reverse_sync(center)
        canvas.setCenter(center)
        canvas.refresh()
        # The canvas echo is suppressed, but all other viewers still need this move.
        self._sync_canvas_center(source=source)

    def _update_roadview_layer(self, lon, lat, pan, tilt, zoom, pano_id):
        if self._project_transitioning:
            return
        return self.display_layers.update_roadview_layer(lon, lat, pan, tilt, zoom, pano_id)

    def _ensure_roadview_layer(self):
        return self.display_layers.ensure_roadview_layer()

    def _remove_roadview_layer(self):
        return self.display_layers.remove_roadview_layer()

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
        if self._project_transitioning:
            return
        epoch = self._project_epoch
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
            self._set_route_status(False, str(exc))
            return

        origin_lon, origin_lat = route_request.origin
        destination_lon, destination_lat = route_request.destination
        waypoints = route_request.waypoints

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

        if epoch != self._project_epoch:
            return
        self._active_route_request = route_request
        self._route_request_epoch = epoch
        self.mobility_client.request_route(rest_key, route_request)

    def _handle_route_failure(self, message):
        self._set_route_status(False, message)

    def _handle_route_result(self, result, route_request):
        epoch = self._project_epoch
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
            "path": self._route_path_payload(points),
            "guides": guides,
        }
        self._create_route_guidance_layer(guides)
        self.active_route_history_id = None
        history_saved = self._append_route_history(
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
        if epoch != self._project_epoch:
            return
        if history_saved:
            self.active_route_history_id = history_id
        else:
            guidance_payload["history_id"] = ""
        self._set_route_guidance(guidance_payload)

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
            self._set_route_status(True, message)
            self.iface.messageBar().pushSuccess("Kakao QGIS Bridge", message)
        else:
            message = "경로는 생성했지만 이력 저장에 실패했습니다. " + message
            self._set_route_status(False, message)
            self.iface.messageBar().pushWarning("Kakao QGIS Bridge", message)

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
        try:
            self.history_repository.append(
                history_id, route_id, searched_at, points, origin, destination,
                origin_label, destination_label, waypoints, distance, duration,
                guidance_count, result_summary, priority, avoid_options,
                vehicle_options, guides,
            )
        except HistoryOperationError as exc:
            self._handle_history_operation_error(exc)
            return False

        if self.save_history_action is not None:
            self.save_history_action.setEnabled(True)
        if self.export_geojson_action is not None:
            self.export_geojson_action.setEnabled(True)
        if self.export_shapefile_action is not None:
            self.export_shapefile_action.setEnabled(True)
        if self.export_gpx_action is not None:
            self.export_gpx_action.setEnabled(True)
        self._sync_route_history_panel(history_id)
        return True

    def _handle_history_operation_error(self, exc):
        QgsMessageLog.logMessage(str(exc), LOG_TAG, MSG_CRITICAL)
        display_message = str(exc)
        try:
            if isinstance(exc, HistoryOperationError) and not exc.recovered:
                route_count = self.route_history_layer.featureCount() if self.route_history_layer is not None else 0
                guide_count = self.guidance_history_layer.featureCount() if self.guidance_history_layer is not None else 0
                display_message += f"\n현재 남은 이력: 경로 {route_count}건, 안내 {guide_count}건."
                if self.active_route_history_id:
                    route = self._route_feature_for_history(self.active_route_history_id)
                    guides = self._guidance_features_for_history(self.active_route_history_id)
                    if route is None or len(guides) != self._safe_number(route["guidance_count"]):
                        self._clear_current_route_display()
            # Recovery can change feature IDs; viewer payloads use history IDs.
            self._sync_route_history_panel(self.active_route_history_id)
            self._update_history_action_state()
        except RuntimeError as refresh_error:
            # An invalid/deleted Qt layer must not suppress the original error UI.
            QgsMessageLog.logMessage(str(refresh_error), LOG_TAG, MSG_WARNING)
        QMessageBox.critical(self.iface.mainWindow(), "Kakao QGIS Bridge", display_message)

    def _ensure_route_history_layers(self):
        return self.history_repository.ensure_layers()

    def _load_route_history_file(self, _checked=False):
        project_home = QgsProject.instance().homePath()
        epoch = self._project_epoch
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
        if not filename or epoch != self._project_epoch:
            return

        input_path = Path(filename)
        try:
            report = self.history_import_service.import_file(input_path)
            route_count, guidance_count = report
        except RuntimeError as exc:
            self._handle_history_operation_error(exc)
            return

        self._update_history_action_state()
        self._sync_route_history_panel()
        if route_count == 0 and guidance_count == 0:
            if report.skipped_routes or report.skipped_guides:
                message = "선택한 파일의 이력이 이미 현재 세션에 있습니다."
            else:
                message = "선택한 파일에 불러올 경로·안내 이력이 없습니다."
        else:
            message = (
                f"경로 이력 불러오기 완료: 경로 {route_count}건, "
                f"안내 {guidance_count}건"
        )
        if report.duplicates or report.skipped_routes or report.skipped_guides:
            message += (f" (기존 경로 {report.skipped_routes}건·안내 {report.skipped_guides}건 건너뜀, "
                        f"파일 중복 {report.duplicates}건 제거)")
            QgsMessageLog.logMessage(
                f"기존 경로 {report.skipped_routes}건·안내 {report.skipped_guides}건 건너뜀, "
                f"파일 내부 중복 {report.duplicates}건 제거", LOG_TAG, MSG_INFO)
        self.iface.messageBar().pushSuccess("Kakao QGIS Bridge", message)
        if report.warnings:
            QgsMessageLog.logMessage("\n".join(report.warnings), LOG_TAG, MSG_WARNING)
            self.iface.messageBar().pushWarning(
                "Kakao QGIS Bridge", f"불러오기 경고 {len(report.warnings)}건: "
                f"{report.warnings[0]} 자세한 내용은 로그 메시지를 확인하세요.")

    def _load_styled_gpx(self, _checked=False):
        project_home = QgsProject.instance().homePath()
        epoch = self._project_epoch
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            "GPX 스타일 적용해서 불러오기",
            project_home or "",
            "GPX (*.gpx)",
        )
        if not filename or epoch != self._project_epoch:
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

    def _sync_route_history_panel(self, selected_history_id=None):
        payload = self._route_history_payload(selected_history_id)
        if self.dock is not None:
            self.dock.set_route_history(payload)
        if self.external_bridge_server is not None:
            self.external_bridge_server.emit_signal(
                "routeHistoryChanged",
                json.dumps(payload, ensure_ascii=False),
            )

    def _refresh_route_history_panel(self):
        self._sync_route_history_panel(self.active_route_history_id)

    def _route_history_payload(self, selected_history_id=None):
        return self.history_ui.payload(selected_history_id)

    def _focus_route_history(self, history_id):
        self.history_ui.focus(history_id)

    def _show_route_history(self, route_feature, guide_features, history_id):
        guidance_payload = self._route_guidance_payload_from_history(
            route_feature,
            guide_features,
        )
        self.active_route_history_id = history_id
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
        if self.external_bridge_server is not None:
            self.external_bridge_server.set_center(center.x(), center.y())
        self._set_route_guidance(guidance_payload)
        self._sync_route_history_panel(history_id)

    def _load_route_history(self, history_id):
        self.history_ui.load_input(history_id)

    def _send_route_history_input(self, route_feature):
        payload = self._route_input_payload_from_history(route_feature)
        if self.dock is not None and self.dock.web_view is not None:
            script = "window.loadRouteHistoryInput({payload});".format(
                payload=json.dumps(payload, ensure_ascii=False)
            )
            self.dock.web_view.page().runJavaScript(script)
        if self.external_bridge_server is not None:
            self.external_bridge_server.emit_signal(
                "loadRouteHistoryInput",
                json.dumps(payload, ensure_ascii=False),
            )

    def _delete_route_history(self, history_id):
        self.history_ui.delete(history_id)

    def _delete_all_route_histories(self):
        self.history_ui.delete_all()

    def _history_export_service(self):
        return HistoryExportService(
            QgsProject.instance().transformContext(),
            route_line_symbol_factory=self.style_factory.route_line_symbol,
            gpx_waypoint_renderer_factory=self.style_factory.gpx_waypoint_renderer,
        )

    def _export_single_route_history(self, history_id):
        return self.history_export_ui._export_single_route_history(history_id)

    def _export_selected_route_histories(self, history_ids_json):
        return self.history_export_ui._export_selected_route_histories(history_ids_json)

    def _export_route_histories(self, history_ids, base_name, dialog_title, success_label):
        return self.history_export_ui._export_route_histories(history_ids, base_name, dialog_title, success_label)

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
        return self.history_repository.route_for_history(history_id)

    def _guidance_features_for_history(self, history_id):
        return self.history_repository.guidance_for_history(history_id)

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
        return HistoryExportController._single_history_layer(source_layer, features, geometry_name, layer_name)

    @staticmethod
    def _history_export_basename(route_feature):
        return HistoryExportController._history_export_basename(route_feature)

    @staticmethod
    def _selected_history_export_basename(history_count):
        return HistoryExportController._selected_history_export_basename(history_count)

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
            "history_id": str(route_feature["history_id"] or ""),
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
            "waypoints": self._waypoints_from_history(route_feature),
            "path": self._route_path_payload(
                self._route_points_from_geometry(route_feature.geometry())
            ),
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
        return history_values.route_points_from_geometry(geometry)

    @staticmethod
    def _route_path_payload(points):
        return [
            {
                "lon": point.x(),
                "lat": point.y(),
            }
            for point in points
        ]

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
        return history_values.safe_number(value)

    @staticmethod
    def _safe_float(value):
        return history_values.safe_float(value)

    def _save_route_history_geopackage(self, _checked=False):
        return self.history_export_ui._save_route_history_geopackage(_checked)

    def _export_route_history_geojson(self, _checked=False):
        return self.history_export_ui._export_route_history_geojson(_checked)

    def _export_route_history_shapefile(self, _checked=False):
        return self.history_export_ui._export_route_history_shapefile(_checked)

    def _export_route_history_gpx(self, _checked=False):
        return self.history_export_ui._export_route_history_gpx(_checked)

    @staticmethod
    def _geojson_output_paths(filename):
        return HistoryExportService._geojson_output_paths(filename)

    @staticmethod
    def _paired_output_paths(filename, extension):
        return HistoryExportService._paired_output_paths(filename, extension)

    def _write_geojson_history_layer(self, source_layer, output_path, layer_name):
        return self._history_export_service().write_geojson_layer(
            source_layer, output_path, layer_name,
        )

    def _shapefile_loss_warning(self, routes, guides):
        return self.history_export_ui._shapefile_loss_warning(routes, guides)

    def _write_shapefile_history_layer(
        self, source_layer, output_path, geometry_name, layer_name, field_specs,
    ):
        return self._history_export_service().write_shapefile_layer(
            source_layer, output_path, geometry_name, layer_name, field_specs,
        )

    def _write_gpx_history(self, route_layer, guidance_layer, output_path):
        return self._history_export_service().write_gpx(
            route_layer, guidance_layer, output_path,
        )

    def _gpx_waypoint_renderer(self):
        return self.style_factory.gpx_waypoint_renderer()


    @staticmethod
    def _waypoints_from_history(route_feature):
        return history_values.waypoints_from_history(route_feature)


    @staticmethod
    def _shapefile_sidecar_paths(path):
        return HistoryExportService._shapefile_sidecar_paths(path)

    @staticmethod
    def _route_shapefile_fields():
        return HistoryExportService._route_shapefile_fields()

    @staticmethod
    def _guidance_shapefile_fields():
        return HistoryExportService._guidance_shapefile_fields()


    def _write_history_layer(
        self, source_layer, output_path, layer_name, geometry_name,
    ):
        return self._history_export_service().write_geopackage_layer(
            source_layer, output_path, layer_name, geometry_name,
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
        layer = self.display_layers.create_route_layer(
            points, distance, duration, guidance_count, result_summary,
            priority, waypoint_count, avoid_options, vehicle_options,
        )
        project = QgsProject.instance()
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
        return self.display_layers.remove_route_layer()

    def _create_route_guidance_layer(self, guides):
        return self.display_layers.create_route_guidance_layer(guides)

    @staticmethod
    def _route_line_symbol():
        return StyleFactory.route_line_symbol()

    def _route_guidance_renderer(self):
        return self.style_factory.route_guidance_renderer()

    @staticmethod
    def _guidance_symbol(filename):
        return StyleFactory.guidance_symbol(filename)

    def _focus_route_guidance(self, sequence, lon, lat):
        if not math.isfinite(lon) or not math.isfinite(lat):
            return
        if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
            return

        self.display_layers.select_guidance(sequence)
        self._handle_viewer_moved(lon, lat)

    def _remove_route_guidance_layer(self):
        return self.display_layers.remove_route_guidance_layer()

    def _clear_current_route_display(self):
        self.active_route_history_id = None
        self._remove_route_layer()
        self._remove_route_guidance_layer()
        payload = {
            "history_id": "",
            "route_id": "",
            "summary": {},
            "path": [],
            "guides": [],
        }
        self._set_route_guidance(payload)

    def _set_route_point(self, point_id, lon, lat):
        if self._project_transitioning:
            return
        return self.display_layers.set_route_point(point_id, lon, lat)

    def _ensure_route_points_layer(self):
        return self.display_layers.ensure_route_points_layer()

    def _sync_route_point_legend(self):
        return self.display_layers.sync_route_point_legend()

    @staticmethod
    def _route_pin_symbol(filename, size=9.0):
        return StyleFactory.route_pin_symbol(filename, size)

    @staticmethod
    def _embedded_svg_path(filename):
        return StyleFactory.embedded_svg_path(filename)

    @staticmethod
    def _route_point_role(point_id):
        return DisplayLayerManager.route_point_role(point_id)

    def _clear_route_point(self, point_id):
        return self.display_layers.clear_route_point(point_id)

    def _clear_route_points(self):
        return self.display_layers.clear_route_points()

    def _remove_route_points_layer(self):
        return self.display_layers.remove_route_points_layer()

    def _set_route_guidance(self, payload):
        self._current_guidance_payload = payload
        if self.dock is not None:
            self.dock.set_route_guidance(payload)
        if self.external_bridge_server is not None:
            self.external_bridge_server.emit_signal(
                "routeGuidanceChanged", json.dumps(payload, ensure_ascii=False)
            )

    def _set_route_status(self, success, message):
        self._last_route_status = (bool(success), str(message))
        if self.dock is not None:
            self.dock.set_route_status(success, message)
        if self.external_bridge_server is not None:
            self.external_bridge_server.emit_signal(
                "routeStatusChanged",
                bool(success),
                str(message),
            )

    def _to_epsg_4326(self, point):
        return self.sync_controller.to_wgs84(point)
