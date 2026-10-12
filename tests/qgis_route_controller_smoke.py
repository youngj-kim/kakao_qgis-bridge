"""Check route orchestration through its explicit callbacks without network/UI."""
import json
import sys
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qgis.core import Qgis
from kakao_qgis_bridge.route_controller import RouteCallbacks, RouteController
from kakao_qgis_bridge.mobility import normalize_route_request


def harness():
    callbacks = {field.name: Mock() for field in fields(RouteCallbacks)}
    state = SimpleNamespace(epoch=0)
    callbacks['transitioning'].return_value = False
    callbacks['current_epoch'].side_effect = lambda: state.epoch
    callbacks['point_ids'].return_value = {'origin': 1, 'waypoint:old': 2}
    callbacks['rest_key'].return_value = 'fixture-key'
    callbacks['append_history'].return_value = True
    callbacks['path_payload'].side_effect = lambda points: [[p.x(), p.y()] for p in points]
    return RouteController(RouteCallbacks(**callbacks)), callbacks, state


args = (127, 37, 127.1, 37.1, 'RECOMMEND', '[]', '[]', '{}', '출발', '도착')
request = normalize_route_request(*args)
result = SimpleNamespace(points=[(127, 37), (127.1, 37.1)], distance=100,
                         duration=20, route_id='fixture', guides=[])
checks = []

controller, cb, state = harness()
controller.request(*args)
cb['clear_point'].assert_called_once_with('waypoint:old')
key, submitted, epoch = cb['submit'].call_args.args
assert key == 'fixture-key' and epoch == 0 and submitted.origin == request.origin
checks.append('normalized request and stale waypoint cleanup')

controller, cb, state = harness()
controller.request(float('nan'), *args[1:])
assert cb['status'].call_args.args[0] is False
cb['submit'].assert_not_called()
cb['set_point'].assert_not_called()
checks.append('invalid request does not mutate pins or submit')

controller, cb, state = harness()
cb['rest_key'].return_value = ''
cb['prompt_rest_key'].return_value = False
controller.request(*args)
cb['submit'].assert_not_called()
assert cb['status'].call_args.args[0] is False
checks.append('key dialog cancellation releases busy via failure status')

controller, cb, state = harness()
cb['rest_key'].return_value = ''
def switch_project():
    state.epoch += 1
    return True
cb['prompt_rest_key'].side_effect = switch_project
controller.request(*args)
cb['submit'].assert_not_called()
checks.append('project change inside key dialog prevents old submission')

controller, cb, state = harness()
controller.handle_result(result, request)
saved = cb['append_history'].call_args.kwargs
payload = cb['guidance'].call_args.args[0]
assert saved['origin'] == request.origin and saved['destination'] == request.destination
assert payload['history_id'] == saved['history_id'] and payload['path'] == [[127, 37], [127.1, 37.1]]
assert cb['status'].call_args.args[0] is True
cb['set_active_history'].assert_called_with(saved['history_id'])
checks.append('result data/identity preserved and successful status')

controller, cb, state = harness()
cb['append_history'].return_value = False
controller.handle_result(result, request)
cb['create_route'].assert_called_once()
assert cb['guidance'].call_args.args[0]['history_id'] == ''
assert cb['status'].call_args.args[0] is False
assert cb['notify'].call_args.args[0] is False
cb['set_active_history'].assert_called_once_with(None)
checks.append('history failure retains route but reports failure without an active ID')

controller, cb, state = harness()
cb['append_history'].side_effect = lambda **kwargs: switch_project()
controller.handle_result(result, request)
cb['guidance'].assert_not_called()
cb['status'].assert_not_called()
checks.append('epoch change during history error UI prevents stale publication')

print('ROUTE_CONTROLLER_RESULT=' + json.dumps(dict(status='ok', qgis=Qgis.QGIS_VERSION, checks=checks)))
