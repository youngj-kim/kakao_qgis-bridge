"""Check result/history pins independently from editable input coordinates."""
import json
import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qgis.core import Qgis, QgsApplication, QgsProject
from qgis.gui import QgsMapCanvas
from kakao_qgis_bridge.plugin import KakaoQgisBridgePlugin
from kakao_qgis_bridge.mobility import normalize_route_request, parse_route_payload

app = QgsApplication([], False)
app.initQgis()
canvas = QgsMapCanvas()
iface = Mock()
iface.mapCanvas.return_value = canvas
plugin = KakaoQgisBridgePlugin(iface)

def pins():
    return {f['point_id']: (f.geometry().asPoint().x(), f.geometry().asPoint().y())
            for f in plugin.route_points_layer.getFeatures()}

try:
    request = normalize_route_request(128, 38, 129, 39, 'RECOMMEND',
        json.dumps([dict(id='waypoint:edited', lon=128.5, lat=38.5)]), '[]', '{}', '출발', '도착')
    payload = dict(trans_id='pins', routes=[dict(result_code=0,
        summary=dict(distance=100, duration=20), sections=[
            dict(roads=[dict(vertexes=[127, 37, 127.1, 37.1])], guides=[
                dict(x=127, y=37, type=100), dict(x=127.1, y=37.1, type=1000)]),
            dict(roads=[dict(vertexes=[127.1, 37.1, 127.2, 37.2])], guides=[
                dict(x=127.2, y=37.2, type=101)])])])
    result = parse_route_payload(payload)
    plugin._set_route_point('waypoint:stale', 130, 40)
    plugin._handle_route_result(result, request)
    expected = dict(origin=(127, 37), destination=(127.2, 37.2))
    expected['waypoint:edited'] = (127.1, 37.1)
    assert pins() == expected, pins()
    # Only the current display hides duplicate pins; guide/history data remains.
    states = {c.value(): c.renderState() for c in plugin.route_guidance_layer.renderer().categories()}
    assert all(not states[c] for c in ('start', 'destination', 'waypoint'))
    assert all(states[c] for c in ('straight', 'left', 'right', 'uturn', 'roundabout', 'transition', 'other'))
    assert plugin.route_guidance_layer.featureCount() == 3
    assert all(c.renderState() for c in plugin.style_factory.route_guidance_renderer().categories())
    history_id = plugin.active_route_history_id
    feature = plugin._route_feature_for_history(history_id)
    assert feature['origin_lon'] == 128 and feature['destination_lon'] == 129
    assert json.loads(feature['waypoints_json'])[0]['lon'] == 128.5
    # Selecting a saved route replaces unrelated current inputs and waypoint IDs.
    plugin._set_route_point('origin', 130, 40)
    plugin._set_route_point('waypoint:stale', 130, 40)
    plugin._focus_route_history(history_id)
    restored = pins()
    assert restored['origin'] == (127, 37) and restored['destination'] == (127.2, 37.2)
    assert restored == expected, restored
    states = {c.value(): c.renderState() for c in plugin.route_guidance_layer.renderer().categories()}
    assert all(not states[c] for c in ('start', 'destination', 'waypoint'))
    # Geometry-only/older history clears stale waypoints, with endpoint fallback.
    plugin._show_route_history(feature, [], history_id)
    assert pins() == dict(origin=(127, 37), destination=(127.2, 37.2))
    assert plugin._route_input_payload_from_history(feature)['origin']['lon'] == 128
    print('ROUTE_PINS_RESULT=' + json.dumps(dict(status='ok', qgis=Qgis.QGIS_VERSION,
        checks=['result pins', 'input preservation', 'history pins', 'missing guides fallback'])))
finally:
    plugin.unload()
    QgsProject.instance().clear()
    app.exitQgis()
