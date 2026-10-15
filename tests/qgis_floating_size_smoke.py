"""Exercise actual Qt dock sizing without WebEngine, SDK or API keys."""
import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qgis.core import QgsApplication, Qgis
from qgis.PyQt.QtCore import Qt, QPoint
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QMainWindow, QWidget
from kakao_qgis_bridge.dock_widget import KakaoMapDockWidget

app = QgsApplication([], True)
app.initQgis()
window = QMainWindow()
window.resize(800, 700)
window.setCentralWidget(QWidget())
with patch('kakao_qgis_bridge.dock_widget.QWebEngineView', None):
    dock = KakaoMapDockWidget(window)
# Isolate native dock mechanics from fallback diagnostic-label size hints.
dock.setWidget(QWidget())
dock.web_view = Mock()
window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
window.show()
app.processEvents()
assert not dock._floating_size_initialized
dock.setFloating(True)
QTest.qWait(150)
assert dock._floating_size_initialized
available = dock.screen().availableGeometry()
assert dock.width() >= min(1100, available.width() - 32)
assert dock.height() >= min(850, available.height() - 48)
assert available.contains(dock.frameGeometry())
assert dock.web_view.hide.called and dock.web_view.show.called
assert 'relayoutKakaoViewer' in dock.web_view.page().runJavaScript.call_args.args[0]
assert not dock.web_view.setHtml.called, 'Dock transition must not reload the viewer'
dock.resize(min(650, available.width() - 32), min(600, available.height() - 48))
app.processEvents()
chosen = dock.size()
dock.setFloating(False)
QTest.qWait(150)
assert not dock.isWindow()
assert window.dockWidgetArea(dock) == Qt.DockWidgetArea.RightDockWidgetArea
assert dock.width() <= window.width() // 2
assert window.centralWidget().width() > 0
dock.setFloating(True)
QTest.qWait(150)
assert dock.size() == chosen, (dock.size(), chosen)
dock.enter_full_screen()
app.processEvents()
dock.exit_full_screen()
QTest.qWait(150)
assert dock.isFloating()
assert dock.size() == chosen
# Qt's own non-native title bar path: double-click must restore the dock layout.
dock.setFloating(False)
QTest.qWait(150)
QTest.mouseDClick(dock, Qt.MouseButton.LeftButton, pos=QPoint(30, 8))
QTest.qWait(150)
assert dock.isFloating(), 'title double-click must undock'
assert dock.size() == chosen
dock.setFloating(False)
QTest.qWait(150)
dock.enter_full_screen()
QTest.qWait(150)
assert dock.isFullScreen()
dock.exit_full_screen()
QTest.qWait(150)
assert not dock.isFloating() and not dock.isWindow()
# A stale pending float callback must not expand an already-redocked widget.
dock.setFloating(True)
dock.setFloating(False)
QTest.qWait(150)
assert not dock.isFloating() and dock.width() <= window.width() // 2
print('FLOATING_SIZE_OK', Qgis.QGIS_VERSION, 'screen bounds/geometry restoration/title double-click/rapid redock/fullscreen')
dock.close()
window.close()
app.exitQgis()
