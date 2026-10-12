import json
import unittest
from unittest.mock import Mock

from kakao_qgis_bridge.viewer_adapter import ViewerAdapter


class ViewerAdapterTests(unittest.TestCase):
    def setUp(self):
        self.dock, self.server = Mock(), Mock()
        self.source = object()
        self.adapter = ViewerAdapter(lambda: self.dock, lambda: self.server, self.source)

    def test_center_preserves_flags_and_source_without_dock_echo(self):
        self.adapter.center(127, 37, source=self.source, update_roadview=False,
                            meters_per_pixel=2, visible_only=True)
        self.dock.set_center.assert_not_called()
        self.server.set_center.assert_called_once_with(
            127, 37, source=None, update_roadview=False, meters_per_pixel=2)

    def test_hidden_dock_policy_and_external_source(self):
        self.dock.isVisible.return_value = False
        self.adapter.center(127, 37, source="tab", visible_only=True)
        self.dock.set_center.assert_not_called()
        self.assertEqual(self.server.set_center.call_args.kwargs["source"], "tab")
        self.adapter.center(128, 38)
        self.dock.set_center.assert_called_once_with(
            128, 38, update_roadview=True, meters_per_pixel=None)

    def test_payload_contracts_and_unicode(self):
        payload = {"label": "한글", "path": [], "guides": []}
        self.adapter.guidance(payload)
        self.dock.set_route_guidance.assert_called_once_with(payload)
        signal, encoded = self.server.emit_signal.call_args.args
        self.assertEqual(signal, "routeGuidanceChanged")
        self.assertEqual(json.loads(encoded), payload)
        self.assertIn("한글", encoded)
        self.adapter.history(payload)
        self.dock.set_route_history.assert_called_once_with(payload)
        self.assertEqual(self.server.emit_signal.call_args.args[0], "routeHistoryChanged")

    def test_input_reset_and_status_contracts(self):
        payload = {"label": "한글\"\n"}
        self.adapter.load_input(payload)
        script = self.dock.web_view.page.return_value.runJavaScript.call_args.args[0]
        self.assertEqual(script, f"window.loadRouteHistoryInput({json.dumps(payload, ensure_ascii=False)});")
        self.assertEqual(self.server.emit_signal.call_args.args[0], "loadRouteHistoryInput")
        self.adapter.reset_project(7)
        self.dock.reset_project.assert_called_once_with(7)
        self.server.emit_signal.assert_called_with("projectReset", 7)
        self.adapter.status(0, 123)
        self.dock.set_route_status.assert_called_once_with(0, 123)
        self.server.emit_signal.assert_called_with("routeStatusChanged", False, "123")

    def test_seed_only_targets_new_server_and_preserves_order(self):
        self.adapter.seed_external(self.server, {"guides": []}, {"items": []}, (False, "완료"))
        self.assertEqual([call.args[0] for call in self.server.emit_signal.call_args_list],
                         ["routeGuidanceChanged", "routeHistoryChanged", "routeStatusChanged"])
        self.assertEqual(self.dock.mock_calls, [])

    def test_current_targets_are_resolved_lazily_and_absence_is_safe(self):
        self.dock, self.server = None, None
        self.adapter.center(127, 37)
        self.adapter.guidance({})
        self.adapter.history({})
        self.adapter.load_input({})
        self.adapter.reset_project(1)
        self.adapter.status(False, "없음")
        self.dock, self.server = Mock(web_view=None), Mock()
        self.adapter.load_input({})
        self.server.emit_signal.assert_called_once_with("loadRouteHistoryInput", "{}")


if __name__ == "__main__":
    unittest.main()
