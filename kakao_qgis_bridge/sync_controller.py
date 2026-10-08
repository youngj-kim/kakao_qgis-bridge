"""QGIS canvas synchronization lifecycle and coordinate transforms."""

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
        if self._applied_center is not None:
            current_crs = canvas.mapSettings().destinationCrs()
            center = canvas.center()
            # Suppress only the expected canvas echo, within a quarter pixel.
            tolerance = max(abs(canvas.mapUnitsPerPixel()) * 0.25, 1e-10)
            if current_crs == self._applied_crs and (
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

    def begin_reverse_sync(self, center):
        self.sync_timer.stop()
        self._applied_center = QgsPointXY(center)
        self._applied_crs = self.iface.mapCanvas().mapSettings().destinationCrs()

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
