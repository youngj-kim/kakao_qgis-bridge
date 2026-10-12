"""QGIS canvas synchronization lifecycle and coordinate transforms."""

import math

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPointXY,
    QgsProject,
)
from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal


class CanvasSyncController(QObject):
    syncRequested = pyqtSignal()

    def __init__(self, iface, has_target, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.has_target = has_target
        self.connected = False
        self.sync_timer = QTimer(self)
        self.sync_timer.setSingleShot(True)
        self.sync_timer.setInterval(350)
        self.sync_timer.timeout.connect(self.syncRequested.emit)
        self._applied_center = None
        self._applied_crs = None
        self._applied_resolution = None
        self._last_view = None
        self.update_roadview = True

    def activate(self):
        canvas = self.iface.mapCanvas()
        newly_connected = not self.connected
        if newly_connected:
            canvas.extentsChanged.connect(self.schedule)
            canvas.destinationCrsChanged.connect(self._crs_changed)
            self.connected = True
        self.schedule()
        return newly_connected

    def deactivate(self):
        canvas = self.iface.mapCanvas()
        self.sync_timer.stop()
        self._applied_center = None
        self._applied_crs = None
        self._last_view = None
        self.update_roadview = True
        if self.connected:
            for signal, callback in (
                (canvas.extentsChanged, self.schedule),
                (canvas.destinationCrsChanged, self._crs_changed),
            ):
                try:
                    signal.disconnect(callback)
                except (RuntimeError, TypeError):
                    pass
            self.connected = False

    def schedule(self, *_args):
        if not self.has_target():
            return
        canvas = self.iface.mapCanvas()
        current_crs = canvas.mapSettings().destinationCrs()
        center = QgsPointXY(canvas.center())
        resolution = abs(canvas.mapUnitsPerPixel())
        previous = self._last_view
        self._last_view = (center, current_crs, resolution)
        # Cursor-anchored zoom changes both resolution and center. It must not
        # select a new panorama. A later pan at the same resolution still does.
        if previous is None or current_crs != previous[1]:
            self.update_roadview = True
        elif not math.isclose(resolution, previous[2], rel_tol=1e-9, abs_tol=1e-12):
            self.update_roadview = False
        elif center != previous[0]:
            self.update_roadview = True
        if self._applied_center is not None:
            # Suppress only the expected canvas echo, within a quarter pixel.
            tolerance = max(abs(canvas.mapUnitsPerPixel()) * 0.25, 1e-10)
            if current_crs == self._applied_crs and (
                self._applied_resolution is None
                or math.isclose(resolution, self._applied_resolution, rel_tol=1e-9)
            ) and (
                abs(center.x() - self._applied_center.x()) <= tolerance
                and abs(center.y() - self._applied_center.y()) <= tolerance
            ):
                return
            self._applied_center = None
            self._applied_crs = None
        self.sync_timer.start()

    def _crs_changed(self, *_args):
        self._applied_center = None
        self._applied_crs = None
        self.schedule()

    def reset_pending(self):
        self.sync_timer.stop()
        self._applied_center = None
        self._applied_crs = None
        self._last_view = None
        self.update_roadview = True

    def begin_reverse_sync(self, center):
        self.sync_timer.stop()
        self._applied_center = QgsPointXY(center)
        self._applied_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        self._applied_resolution = abs(self.iface.mapCanvas().mapUnitsPerPixel())

    def meters_per_pixel(self, center=None):
        """Ground resolution in meters, independent of the project CRS units."""
        canvas = self.iface.mapCanvas()
        center = canvas.center() if center is None else center
        half_span = abs(canvas.mapUnitsPerPixel()) * 64
        lon1, lat1 = self.to_wgs84(QgsPointXY(center.x() - half_span, center.y()))
        lon2, lat2 = self.to_wgs84(QgsPointXY(center.x() + half_span, center.y()))
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        a = (math.sin((phi2 - phi1) / 2) ** 2
             + math.cos(phi1) * math.cos(phi2)
             * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
        resolution = 6371008.8 * 2 * math.asin(math.sqrt(min(1, max(0, a)))) / 128
        if not math.isfinite(resolution) or resolution <= 0:
            raise ValueError("지도 확대 비율을 계산하지 못했습니다.")
        return resolution

    def to_wgs84(self, point):
        canvas = self.iface.mapCanvas()
        transform = QgsCoordinateTransform(
            canvas.mapSettings().destinationCrs(),
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance(),
        )
        transformed = transform.transform(point)
        return transformed.x(), transformed.y()

    def from_wgs84(self, lon, lat):
        canvas = self.iface.mapCanvas()
        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"),
            canvas.mapSettings().destinationCrs(),
            QgsProject.instance(),
        )
        return transform.transform(QgsPointXY(lon, lat))
