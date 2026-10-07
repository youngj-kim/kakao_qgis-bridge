"""Signal/timer tests without QGIS; real canvas behavior is in the smoke test."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


class Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def disconnect(self, callback):
        self.callbacks.remove(callback)

    def emit(self, *args):
        for callback in list(self.callbacks):
            callback(*args)


class Timer:
    def __init__(self, parent=None):
        self.timeout = Signal()
        self.active = False
        self.starts = 0

    def setSingleShot(self, value):
        self.single_shot = value

    def setInterval(self, value):
        self.interval = value

    def start(self):
        self.active = True
        self.starts += 1

    def stop(self):
        self.active = False


class Point:
    def __init__(self, x, y=None):
        self.coords = (x.x(), x.y()) if y is None else (x, y)

    def x(self):
        return self.coords[0]

    def y(self):
        return self.coords[1]


def load_controller():
    class QObject:
        def __init__(self, parent=None):
            pass
    core = types.ModuleType("qgis.core")
    core.QgsCoordinateReferenceSystem = MagicMock()
    core.QgsCoordinateTransform = MagicMock()
    core.QgsPointXY = Point
    core.QgsProject = MagicMock()
    qt = types.ModuleType("qgis.PyQt.QtCore")
    qt.QObject, qt.QTimer, qt.pyqtSignal = QObject, Timer, lambda: Signal()
    path = Path(__file__).resolve().parents[1] / "kakao_qgis_bridge" / "sync_controller.py"
    spec = importlib.util.spec_from_file_location("kakao_qgis_bridge._test_sync", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"qgis.core": core, "qgis.PyQt.QtCore": qt}):
        spec.loader.exec_module(module)
    return module


controller_module = load_controller()


class CanvasSyncTests(unittest.TestCase):
    def setUp(self):
        self.center = Point(100, 200)
        self.crs = "EPSG:3857"
        self.resolution = 4
        self.has_target = True
        self.canvas = types.SimpleNamespace(
            extentsChanged=Signal(), destinationCrsChanged=Signal(),
            center=lambda: self.center, mapUnitsPerPixel=lambda: self.resolution,
            mapSettings=lambda: types.SimpleNamespace(destinationCrs=lambda: self.crs),
        )
        self.controller = controller_module.CanvasSyncController(
            types.SimpleNamespace(mapCanvas=lambda: self.canvas), lambda: self.has_target
        )

    def test_expected_echo_is_suppressed_but_immediate_user_move_is_scheduled(self):
        self.controller.begin_reverse_sync(Point(100, 200))
        self.controller.schedule()
        self.assertFalse(self.controller.sync_timer.active)
        self.center = Point(110, 210)
        self.controller.schedule()
        self.assertTrue(self.controller.sync_timer.active)

    def test_small_canvas_rounding_is_suppressed_with_pixel_tolerance(self):
        self.controller.begin_reverse_sync(self.center)
        self.center = Point(100.5, 200.5)
        self.controller.schedule()
        self.assertFalse(self.controller.sync_timer.active)
        self.center = Point(101.1, 200)
        self.controller.schedule()
        self.assertTrue(self.controller.sync_timer.active)

    def test_crs_change_invalidates_guard_even_at_same_numeric_center(self):
        self.controller.activate()
        self.controller.begin_reverse_sync(self.center)
        self.crs = "EPSG:4326"
        self.canvas.destinationCrsChanged.emit()
        self.assertTrue(self.controller.sync_timer.active)
        self.assertIsNone(self.controller._applied_center)

    def test_crs_difference_is_detected_without_signal(self):
        self.controller.begin_reverse_sync(self.center)
        self.crs = "EPSG:4326"
        self.controller.schedule()
        self.assertTrue(self.controller.sync_timer.active)

    def test_new_reverse_move_cancels_pending_forward_move(self):
        self.controller.schedule()
        self.assertTrue(self.controller.sync_timer.active)
        self.controller.begin_reverse_sync(Point(300, 400))
        self.center = Point(300, 400)
        self.controller.schedule()
        self.assertFalse(self.controller.sync_timer.active)

    def test_lifecycle_does_not_duplicate_signal_connections(self):
        self.assertTrue(self.controller.activate())
        self.assertFalse(self.controller.activate())
        self.assertEqual(len(self.canvas.extentsChanged.callbacks), 1)
        self.controller.begin_reverse_sync(self.center)
        self.controller.deactivate()
        self.assertEqual(self.canvas.extentsChanged.callbacks, [])
        self.assertEqual(self.canvas.destinationCrsChanged.callbacks, [])
        self.assertIsNone(self.controller._applied_center)
        self.assertFalse(self.controller.sync_timer.active)
        self.controller.activate()
        self.assertTrue(self.controller.sync_timer.active)

    def test_no_target_does_not_schedule(self):
        self.has_target = False
        self.controller.schedule()
        self.assertFalse(self.controller.sync_timer.active)
