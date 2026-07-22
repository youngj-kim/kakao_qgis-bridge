import json
import math

from qgis.PyQt.QtCore import QObject, Qt, QUrl, pyqtSignal, pyqtSlot
from qgis.PyQt.QtGui import QDesktopServices, QKeySequence
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    from qgis.PyQt.QtGui import QShortcut
except ImportError:
    from qgis.PyQt.QtWidgets import QShortcut


WEB_RUNTIME_IMPORT_ERRORS = []


def _record_import_error(component, primary_error, fallback_error):
    WEB_RUNTIME_IMPORT_ERRORS.append(
        {
            "component": component,
            "primary_error": str(primary_error),
            "fallback_error": str(fallback_error),
        }
    )


try:
    from qgis.PyQt.QtWebChannel import QWebChannel
except ImportError as primary_error:
    try:
        from PyQt5.QtWebChannel import QWebChannel
    except ImportError as fallback_error:
        QWebChannel = None
        _record_import_error(
            "Qt WebChannel",
            primary_error,
            fallback_error,
        )

try:
    from qgis.PyQt.QtWebEngineWidgets import QWebEngineView
except ImportError as primary_error:
    try:
        from PyQt5.QtWebEngineWidgets import QWebEngineView
    except ImportError as fallback_error:
        QWebEngineView = None
        _record_import_error(
            "Qt WebEngine",
            primary_error,
            fallback_error,
        )

from .settings import PLUGIN_DIR, kakao_javascript_key, kakao_map_base_url


def web_runtime_diagnostic():
    if QWebEngineView is not None and QWebChannel is not None:
        return ""

    lines = [
        "QGIS 3에서는 내장 지도 창 대신 외부 브라우저 연동 모드를 사용합니다.",
        "아래의 외부 연동 창 열기 버튼을 누르면 Kakao Map/Roadview가 기본 브라우저에서 열리고 QGIS와 위치가 동기화됩니다.",
        "QGIS 캔버스를 이동하면 외부 Kakao 지도와 Roadview가 따라 이동하며, 외부 Kakao 지도나 Roadview에서 이동한 위치도 QGIS에 반영됩니다.",
    ]

    return "\n".join(lines)


class KakaoWebBridge(QObject):
    centerRequested = pyqtSignal(float, float)
    roadviewStateChanged = pyqtSignal(float, float, float, float, float, str)
    routeRequested = pyqtSignal(
        float, float, float, float, str, str, str, str, str, str
    )
    routePointChanged = pyqtSignal(str, float, float)
    routePointCleared = pyqtSignal(str)
    routePointsCleared = pyqtSignal()
    routeStatusChanged = pyqtSignal(bool, str)
    routeGuidanceChanged = pyqtSignal(str)
    routeGuidanceSelected = pyqtSignal(int, float, float)
    routeHistoryChanged = pyqtSignal(str)
    routeHistorySelected = pyqtSignal(str)
    routeHistoryFileLoadRequested = pyqtSignal()
    routeHistoryLoadRequested = pyqtSignal(str)
    routeHistoryDeleteRequested = pyqtSignal(str)
    routeHistoriesDeleteRequested = pyqtSignal()
    routeHistoryExportRequested = pyqtSignal(str)
    routeHistoriesExportRequested = pyqtSignal(str)
    routeHistoryRefreshRequested = pyqtSignal()
    externalViewerRequested = pyqtSignal()
    fullScreenRequested = pyqtSignal()

    @pyqtSlot(float, float)
    def moveQgisCenter(self, lon, lat):
        self.centerRequested.emit(lon, lat)

    @pyqtSlot(float, float)
    def openKakaoRoadview(self, lon, lat):
        if not math.isfinite(lon) or not math.isfinite(lat):
            return
        if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
            return

        url = QUrl(
            "https://map.kakao.com/link/roadview/"
            f"{lat:.8f},{lon:.8f}"
        )
        QDesktopServices.openUrl(url)

    @pyqtSlot(float, float, float, float, float, str)
    def updateRoadviewState(self, lon, lat, pan, tilt, zoom, pano_id):
        self.roadviewStateChanged.emit(
            lon,
            lat,
            pan,
            tilt,
            zoom,
            pano_id,
        )

    @pyqtSlot(float, float, float, float, str, str, str, str, str, str)
    def requestRoute(
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
        self.routeRequested.emit(
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

    @pyqtSlot(str, float, float)
    def setRoutePoint(self, role, lon, lat):
        self.routePointChanged.emit(role, lon, lat)

    @pyqtSlot(str)
    def clearRoutePoint(self, role):
        self.routePointCleared.emit(role)

    @pyqtSlot()
    def clearRoutePoints(self):
        self.routePointsCleared.emit()

    @pyqtSlot(int, float, float)
    def selectRouteGuidance(self, sequence, lon, lat):
        self.routeGuidanceSelected.emit(sequence, lon, lat)

    @pyqtSlot(str)
    def selectRouteHistory(self, history_id):
        self.routeHistorySelected.emit(history_id)

    @pyqtSlot()
    def loadRouteHistoryFile(self):
        self.routeHistoryFileLoadRequested.emit()

    @pyqtSlot(str)
    def loadRouteHistory(self, history_id):
        self.routeHistoryLoadRequested.emit(history_id)

    @pyqtSlot(str)
    def deleteRouteHistory(self, history_id):
        self.routeHistoryDeleteRequested.emit(history_id)

    @pyqtSlot()
    def deleteAllRouteHistories(self):
        self.routeHistoriesDeleteRequested.emit()

    @pyqtSlot(str)
    def exportRouteHistory(self, history_id):
        self.routeHistoryExportRequested.emit(history_id)

    @pyqtSlot(str)
    def exportRouteHistories(self, history_ids_json):
        self.routeHistoriesExportRequested.emit(history_ids_json)

    @pyqtSlot()
    def refreshRouteHistory(self):
        self.routeHistoryRefreshRequested.emit()

    @pyqtSlot()
    def openExternalViewer(self):
        self.externalViewerRequested.emit()

    @pyqtSlot()
    def toggleFullScreen(self):
        self.fullScreenRequested.emit()


class KakaoMapDockWidget(QDockWidget):
    centerRequested = pyqtSignal(float, float)
    roadviewStateChanged = pyqtSignal(float, float, float, float, float, str)
    routeRequested = pyqtSignal(
        float, float, float, float, str, str, str, str, str, str
    )
    routePointChanged = pyqtSignal(str, float, float)
    routePointCleared = pyqtSignal(str)
    routePointsCleared = pyqtSignal()
    routeGuidanceSelected = pyqtSignal(int, float, float)
    routeHistorySelected = pyqtSignal(str)
    routeHistoryFileLoadRequested = pyqtSignal()
    routeHistoryLoadRequested = pyqtSignal(str)
    routeHistoryDeleteRequested = pyqtSignal(str)
    routeHistoriesDeleteRequested = pyqtSignal()
    routeHistoryExportRequested = pyqtSignal(str)
    routeHistoriesExportRequested = pyqtSignal(str)
    routeHistoryRefreshRequested = pyqtSignal()
    externalViewerRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Kakao Map / Roadview", parent)
        self.web_view = None
        self.web_bridge = None
        self.web_channel = None
        self.web_runtime_diagnostic = web_runtime_diagnostic()
        self.full_screen_restore_floating = None
        self.fallback_lon = None
        self.fallback_lat = None
        self.fallback_coordinate_label = None
        self.fallback_external_button = None
        self.fallback_map_button = None
        self.fallback_roadview_button = None

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        if self.web_runtime_diagnostic:
            self._configure_external_browser_fallback(layout, container)
        else:
            self.web_view = QWebEngineView(container)
            layout.addWidget(self.web_view)
            self._configure_web_channel()
            self._load_viewer()

        self.setWidget(container)
        escape_key = getattr(Qt, "Key_Escape", None)
        if escape_key is None:
            escape_key = Qt.Key.Key_Escape
        self._escape_shortcut = QShortcut(QKeySequence(escape_key), self)
        self._escape_shortcut.activated.connect(self.exit_full_screen)

    def set_center(self, lon, lat):
        if self.web_view is None:
            self._set_fallback_center(lon, lat)
            return

        script = "window.centerKakaoMap({lon}, {lat});".format(
            lon=json.dumps(float(lon)),
            lat=json.dumps(float(lat)),
        )
        self.web_view.page().runJavaScript(script)

    def reload_viewer(self):
        if self.web_view is not None:
            self._load_viewer()

    def toggle_full_screen(self):
        if self.isFullScreen():
            self.exit_full_screen()
        else:
            self.enter_full_screen()

    def enter_full_screen(self):
        self.full_screen_restore_floating = self.isFloating()
        if not self.isFloating():
            self.setFloating(True)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def exit_full_screen(self):
        if not self.isFullScreen():
            return

        restore_floating = self.full_screen_restore_floating
        self.showNormal()
        if restore_floating is False:
            self.setFloating(False)
        self.full_screen_restore_floating = None

    def set_route_status(self, success, message):
        if self.web_bridge is not None:
            self.web_bridge.routeStatusChanged.emit(bool(success), str(message))

    def set_route_guidance(self, payload):
        if self.web_bridge is not None:
            self.web_bridge.routeGuidanceChanged.emit(
                json.dumps(payload, ensure_ascii=False)
            )

    def set_route_history(self, payload):
        if self.web_bridge is not None:
            self.web_bridge.routeHistoryChanged.emit(
                json.dumps(payload, ensure_ascii=False)
            )

    def _configure_web_channel(self):
        self.web_bridge = KakaoWebBridge(self)
        self.web_bridge.centerRequested.connect(self.centerRequested.emit)
        self.web_bridge.roadviewStateChanged.connect(
            self.roadviewStateChanged.emit
        )
        self.web_bridge.routeRequested.connect(self.routeRequested.emit)
        self.web_bridge.routePointChanged.connect(self.routePointChanged.emit)
        self.web_bridge.routePointCleared.connect(self.routePointCleared.emit)
        self.web_bridge.routePointsCleared.connect(self.routePointsCleared.emit)
        self.web_bridge.routeGuidanceSelected.connect(
            self.routeGuidanceSelected.emit
        )
        self.web_bridge.routeHistorySelected.connect(
            self.routeHistorySelected.emit
        )
        self.web_bridge.routeHistoryFileLoadRequested.connect(
            self.routeHistoryFileLoadRequested.emit
        )
        self.web_bridge.routeHistoryLoadRequested.connect(
            self.routeHistoryLoadRequested.emit
        )
        self.web_bridge.routeHistoryDeleteRequested.connect(
            self.routeHistoryDeleteRequested.emit
        )
        self.web_bridge.routeHistoriesDeleteRequested.connect(
            self.routeHistoriesDeleteRequested.emit
        )
        self.web_bridge.routeHistoryExportRequested.connect(
            self.routeHistoryExportRequested.emit
        )
        self.web_bridge.routeHistoriesExportRequested.connect(
            self.routeHistoriesExportRequested.emit
        )
        self.web_bridge.routeHistoryRefreshRequested.connect(
            self.routeHistoryRefreshRequested.emit
        )
        self.web_bridge.externalViewerRequested.connect(
            self.externalViewerRequested.emit
        )
        self.web_bridge.fullScreenRequested.connect(self.toggle_full_screen)

        self.web_channel = QWebChannel(self.web_view.page())
        self.web_channel.registerObject("qgisBridge", self.web_bridge)
        self.web_view.page().setWebChannel(self.web_channel)

    def _configure_external_browser_fallback(self, layout, container):
        message = QLabel(self.web_runtime_diagnostic, container)
        message.setWordWrap(True)
        layout.addWidget(message)

        self.fallback_coordinate_label = QLabel(
            "QGIS 캔버스 중심 좌표를 기다리는 중입니다.",
            container,
        )
        self.fallback_coordinate_label.setWordWrap(True)
        layout.addWidget(self.fallback_coordinate_label)

        button_row = QHBoxLayout()
        self.fallback_external_button = QPushButton("외부 연동 창 열기", container)
        self.fallback_external_button.clicked.connect(
            self.externalViewerRequested.emit
        )
        button_row.addWidget(self.fallback_external_button)

        self.fallback_map_button = QPushButton("카카오맵 열기", container)
        self.fallback_map_button.setEnabled(False)
        self.fallback_map_button.clicked.connect(self.open_external_map)
        button_row.addWidget(self.fallback_map_button)

        self.fallback_roadview_button = QPushButton("로드뷰 열기", container)
        self.fallback_roadview_button.setEnabled(False)
        self.fallback_roadview_button.clicked.connect(
            self.open_external_roadview
        )
        button_row.addWidget(self.fallback_roadview_button)
        layout.addLayout(button_row)

        layout.addStretch(1)

    def _set_fallback_center(self, lon, lat):
        try:
            lon = float(lon)
            lat = float(lat)
        except (TypeError, ValueError):
            return

        if not math.isfinite(lon) or not math.isfinite(lat):
            return
        if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
            return

        self.fallback_lon = lon
        self.fallback_lat = lat
        if self.fallback_coordinate_label is not None:
            self.fallback_coordinate_label.setText(
                "현재 QGIS 중심 좌표: "
                f"EPSG:4326 {lat:.8f}, {lon:.8f}"
            )
        for button in (self.fallback_map_button, self.fallback_roadview_button):
            if button is not None:
                button.setEnabled(True)

    def open_external_map(self):
        if self.fallback_lon is None or self.fallback_lat is None:
            return

        url = QUrl(
            "https://map.kakao.com/link/map/"
            f"Kakao%20QGIS%20Bridge,{self.fallback_lat:.8f},"
            f"{self.fallback_lon:.8f}"
        )
        QDesktopServices.openUrl(url)

    def open_external_roadview(self):
        if self.fallback_lon is None or self.fallback_lat is None:
            return

        url = QUrl(
            "https://map.kakao.com/link/roadview/"
            f"{self.fallback_lat:.8f},{self.fallback_lon:.8f}"
        )
        QDesktopServices.openUrl(url)

    def _load_viewer(self):
        template_path = PLUGIN_DIR / "web" / "kakao_viewer.html"
        html = template_path.read_text(encoding="utf-8")
        html = html.replace(
            "__KAKAO_APP_KEY_JSON__",
            json.dumps(kakao_javascript_key()),
        )

        self.web_view.setHtml(html, QUrl(kakao_map_base_url()))
