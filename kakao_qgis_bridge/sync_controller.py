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
        self.reverse_guard = QTimer(self)
        self.reverse_guard.setSingleShot(True)
        self.reverse_guard.setInterval(600)

    def activate(self):
        canvas = self.iface.mapCanvas()
        newly_connected = not self.connected
        if newly_connected:
            canvas.extentsChanged.connect(self.schedule)
            canvas.destinationCrsChanged.connect(self.schedule)
            self.connected = True
        self.schedule()
        return newly_connected

    def deactivate(self):
        canvas = self.iface.mapCanvas()
        self.sync_timer.stop()
        self.reverse_guard.stop()
        if self.connected:
            for signal in (canvas.extentsChanged, canvas.destinationCrsChanged):
                try:
                    signal.disconnect(self.schedule)
                except (RuntimeError, TypeError):
                    pass
            self.connected = False

    def schedule(self, *_args):
        if self.has_target() and not self.reverse_guard.isActive():
            self.sync_timer.start()

    def begin_reverse_sync(self):
        self.sync_timer.stop()
        self.reverse_guard.start()

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
