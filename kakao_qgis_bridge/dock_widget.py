import json
import math

from qgis.PyQt.QtCore import QObject, QUrl, pyqtSignal, pyqtSlot
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QLabel, QVBoxLayout, QWidget, QDockWidget

try:
    from qgis.PyQt.QtWebChannel import QWebChannel
except ImportError:
    try:
        from PyQt5.QtWebChannel import QWebChannel
    except ImportError:
        QWebChannel = None

try:
    from qgis.PyQt.QtWebEngineWidgets import QWebEngineView
except ImportError:
    try:
        from PyQt5.QtWebEngineWidgets import QWebEngineView
    except ImportError:
        QWebEngineView = None

from .settings import PLUGIN_DIR, kakao_javascript_key, kakao_map_base_url


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
    routeHistoryLoadRequested = pyqtSignal(str)
    routeHistoryDeleteRequested = pyqtSignal(str)
    routeHistoryExportRequested = pyqtSignal(str)

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

    @pyqtSlot(str)
    def loadRouteHistory(self, history_id):
        self.routeHistoryLoadRequested.emit(history_id)

    @pyqtSlot(str)
    def deleteRouteHistory(self, history_id):
        self.routeHistoryDeleteRequested.emit(history_id)

    @pyqtSlot(str)
    def exportRouteHistory(self, history_id):
        self.routeHistoryExportRequested.emit(history_id)


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
    routeHistoryLoadRequested = pyqtSignal(str)
    routeHistoryDeleteRequested = pyqtSignal(str)
    routeHistoryExportRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__("Kakao Map / Roadview", parent)
        self.web_view = None
        self.web_bridge = None
        self.web_channel = None

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        if QWebEngineView is None or QWebChannel is None:
            message = QLabel(
                (
                    "Qt WebEngine/WebChannel is not available in this "
                    "QGIS Python environment."
                ),
                container,
            )
            message.setWordWrap(True)
            layout.addWidget(message)
        else:
            self.web_view = QWebEngineView(container)
            layout.addWidget(self.web_view)
            self._configure_web_channel()
            self._load_viewer()

        self.setWidget(container)

    def set_center(self, lon, lat):
        if self.web_view is None:
            return

        script = "window.centerKakaoMap({lon}, {lat});".format(
            lon=json.dumps(float(lon)),
            lat=json.dumps(float(lat)),
        )
        self.web_view.page().runJavaScript(script)

    def reload_viewer(self):
        if self.web_view is not None:
            self._load_viewer()

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
        self.web_bridge.routeHistoryLoadRequested.connect(
            self.routeHistoryLoadRequested.emit
        )
        self.web_bridge.routeHistoryDeleteRequested.connect(
            self.routeHistoryDeleteRequested.emit
        )
        self.web_bridge.routeHistoryExportRequested.connect(
            self.routeHistoryExportRequested.emit
        )

        self.web_channel = QWebChannel(self.web_view.page())
        self.web_channel.registerObject("qgisBridge", self.web_bridge)
        self.web_view.page().setWebChannel(self.web_channel)

    def _load_viewer(self):
        template_path = PLUGIN_DIR / "web" / "kakao_viewer.html"
        html = template_path.read_text(encoding="utf-8")
        html = html.replace(
            "__KAKAO_APP_KEY_JSON__",
            json.dumps(kakao_javascript_key()),
        )

        self.web_view.setHtml(html, QUrl(kakao_map_base_url()))
