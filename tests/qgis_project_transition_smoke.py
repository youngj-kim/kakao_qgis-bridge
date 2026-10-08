"""Check project boundaries with real QGIS layers and Qt reply handling."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from qgis.core import Qgis, QgsApplication, QgsProject, QgsVectorLayer
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkReply
from kakao_qgis_bridge.plugin import KakaoQgisBridgePlugin
from kakao_qgis_bridge.compat import MSGBOX_YES
from kakao_qgis_bridge.external_bridge import KakaoExternalBridgeServer
from kakao_qgis_bridge.mobility import normalize_route_request, parse_route_payload


class FixtureReply(QObject):
    finished = pyqtSignal()

    def __init__(self, payload):
        super().__init__()
        self.payload = payload
        self.aborted = False

    def abort(self):
        self.aborted = True

    def attribute(self, _name):
        return 200

    def readAll(self):
        return json.dumps(self.payload).encode()

    def error(self):
        return QNetworkReply.NetworkError.NoError

    def errorString(self):
        return ""


app = QgsApplication([], False)
app.initQgis()
canvas = QgsMapCanvas()
iface = Mock()
iface.mainWindow.return_value = None
iface.mapCanvas.return_value = canvas
project = QgsProject.instance()
fixture = root / "dist" / f"project-boundary-{os.getpid()}.qgs"
blank = QgsProject()
user_layer = QgsVectorLayer("Point?crs=EPSG:4326", "Kakao Mobility Route", "memory")
blank.addMapLayer(user_layer)
user_id = user_layer.id()
assert blank.write(str(fixture))
payload = dict(trans_id="fixture", routes=[dict(result_code=0,
    summary=dict(distance=1200, duration=180), sections=[dict(
        roads=[dict(vertexes=[126.9, 37.5, 127.0, 37.6])],
        guides=[dict(x=126.9, y=37.5, type=2, guidance="안내")])])])
request_args = (126.9, 37.5, 127.0, 37.6, "RECOMMEND", "[]", "[]", "{}", "출발", "도착")
request = normalize_route_request(*request_args)
result = parse_route_payload(payload)
checks = []
plugin = None
try:
    for transition in ("clear", "read"):
        project.clear()
        plugin = KakaoQgisBridgePlugin(iface)
        plugin.initGui()
        plugin.dock = Mock()
        plugin.dock.isVisible.return_value = False
        bridge = KakaoExternalBridgeServer(port=0)
        plugin.external_bridge_server = bridge
        plugin._handle_route_result(result, request)
        hid = plugin.active_route_history_id
        plugin.route_history_layer.selectAll()
        plugin.history_repository._operations.needs_recovery = True
        before_count = plugin.route_history_layer.featureCount()
        old_reply = FixtureReply(payload)
        with patch('kakao_qgis_bridge.plugin.kakao_rest_api_key', return_value='fixture-key'), \
             patch.object(plugin.mobility_client._manager, 'get', return_value=old_reply):
            plugin._request_route(*request_args)
        old_request = plugin._active_route_request
        assert old_request is not None
        bridge.emit_signal('loadRouteHistoryInput', 'old command')
        bridge.queue_event(dict(type='route_point', payload=dict(role='origin', lon=126.9, lat=37.5)))
        rejected = []
        def during_clear():
            rejected.append(not bridge.queue_event(dict(type='route_point', payload={})))
        project.aboutToBeCleared.connect(during_clear)
        if transition == "clear":
            project.clear()
        else:
            assert project.read(str(fixture))
        project.aboutToBeCleared.disconnect(during_clear)
        assert rejected == [True]
        assert plugin.route_history_layer.featureCount() == before_count
        assert plugin.history_repository.needs_recovery
        assert plugin.route_history_layer.selectedFeatureCount() == 0
        assert plugin.active_route_history_id is None and not plugin._current_guidance_payload['path']
        assert plugin.route_layer is None and plugin.route_points_layer is None
        assert old_reply.aborted and plugin.mobility_client._reply is None
        assert bridge.drain_events() == []
        state = bridge.events_since(0)['snapshot']['signals']
        assert not json.loads(state['routeGuidanceChanged']['args'][0])['path']
        assert json.loads(state['routeHistoryChanged']['args'][0])['selected_history_id'] == ''
        assert 'projectReset' in state
        assert bridge._center is None
        if transition == 'read':
            assert project.mapLayer(user_id) is not None
        plugin.mobility_client._handle_reply(old_reply, old_request)
        plugin.mobility_client.succeeded.emit(result, old_request)
        plugin.mobility_client.failed.emit('late failure')
        assert plugin.route_history_layer.featureCount() == before_count and plugin.route_layer is None
        assert '프로젝트가 변경' in plugin._last_route_status[1]
        plugin.history_repository._operations.needs_recovery = False
        new_reply = FixtureReply(payload)
        with patch('kakao_qgis_bridge.plugin.kakao_rest_api_key', return_value='fixture-key'), \
             patch.object(plugin.mobility_client._manager, 'get', return_value=new_reply):
            plugin._request_route(*request_args)
        new_request = plugin._active_route_request
        plugin.mobility_client.succeeded.emit(result, old_request)
        assert plugin.route_history_layer.featureCount() == before_count
        plugin.mobility_client._handle_reply(new_reply, new_request)
        assert plugin.route_history_layer.featureCount() == before_count + 1
        assert plugin.active_route_history_id and plugin._last_route_status[0]
        # Individual layer deletion keeps the active session and recreates lazily.
        active = plugin.active_route_history_id
        project.removeMapLayer(plugin.route_layer.id())
        assert plugin.active_route_history_id == active
        plugin._focus_route_history(active)
        assert project.mapLayer(plugin.route_layer.id()) is not None
        # Project switch inside a confirmation cancels both the command and tail.
        def switch_in_question(*_args):
            project.clear()
            return MSGBOX_YES
        bridge.queue_event(dict(type='delete_route_history', payload=dict(history_id=hid)))
        bridge.queue_event(dict(type='route_point', payload=dict(role='origin', lon=126.9, lat=37.5)))
        with patch('kakao_qgis_bridge.plugin.QMessageBox.question', side_effect=switch_in_question):
            plugin._process_external_bridge_events()
        assert plugin.history_repository.route_for_history(hid) is not None
        assert plugin.route_points_layer is None
        # A file dialog crossing the boundary cannot resume an old load.
        def switch_in_file_dialog(*_args):
            project.clear()
            return str(fixture), ''
        with patch('kakao_qgis_bridge.plugin.QFileDialog.getOpenFileName', side_effect=switch_in_file_dialog), \
             patch.object(plugin.history_import_service, 'import_file') as importer:
            plugin._load_route_history_file()
            importer.assert_not_called()
        # Export UI checks the same real project boundary after every modal.
        def switch_in_format(*_args):
            project.clear()
            return "GPX (*.gpx)", True
        with patch('kakao_qgis_bridge.plugin.QInputDialog.getItem', side_effect=switch_in_format), \
             patch('kakao_qgis_bridge.plugin.QFileDialog.getSaveFileName') as save, \
             patch.object(plugin, '_write_gpx_history') as writer:
            plugin._export_single_route_history(hid)
            save.assert_not_called()
            writer.assert_not_called()
        exports = (
            (plugin._save_route_history_geopackage, '_write_history_layer'),
            (plugin._export_route_history_geojson, '_write_geojson_history_layer'),
            (plugin._export_route_history_shapefile, '_write_shapefile_history_layer'),
            (plugin._export_route_history_gpx, '_write_gpx_history'),
        )
        for export, writer_name in exports:
            with patch('kakao_qgis_bridge.plugin.QFileDialog.getSaveFileName',
                       side_effect=switch_in_file_dialog), \
                 patch.object(plugin, writer_name) as writer:
                export()
                writer.assert_not_called()
        for export, writer_name in exports[1:]:
            with patch('kakao_qgis_bridge.plugin.QFileDialog.getSaveFileName',
                       return_value=(str(fixture.with_suffix('.gpx')), '')), \
                 patch('pathlib.Path.exists', return_value=True), \
                 patch('kakao_qgis_bridge.plugin.QMessageBox.question',
                       side_effect=switch_in_question), \
                 patch.object(plugin, writer_name) as writer:
                export()
                writer.assert_not_called()
        before_epoch = plugin._project_epoch
        plugin.unload()
        project.clear()
        assert plugin._project_epoch == before_epoch
        checks.append(transition + ': history/recovery preserved, state reset, old replies/queue/modal blocked, new request works, unload disconnects')
        plugin = None
    print('PROJECT_BOUNDARY_RESULT=' + json.dumps(dict(qgis=Qgis.QGIS_VERSION, checks=checks)), flush=True)
finally:
    if plugin is not None:
        plugin.unload()
    project.clear()
    del blank
    fixture.unlink(missing_ok=True)
    fixture.with_suffix('.qgs~').unlink(missing_ok=True)
    app.exitQgis()
