"""One outbound contract for dock and authenticated external viewers."""

import json


class ViewerAdapter:
    def __init__(self, get_dock, get_external, dock_source):
        self.get_dock = get_dock
        self.get_external = get_external
        self.dock_source = dock_source

    def center(self, lon, lat, source=None, update_roadview=True,
               meters_per_pixel=None, visible_only=False):
        dock = self.get_dock()
        if (source is not self.dock_source and dock is not None
                and (not visible_only or dock.isVisible())):
            dock.set_center(lon, lat, update_roadview=update_roadview,
                            meters_per_pixel=meters_per_pixel)
        server = self.get_external()
        if server is not None:
            server.set_center(lon, lat,
                              source=None if source is self.dock_source else source,
                              update_roadview=update_roadview,
                              meters_per_pixel=meters_per_pixel)

    def _payload(self, method, signal, payload):
        dock = self.get_dock()
        if dock is not None:
            getattr(dock, method)(payload)
        server = self.get_external()
        if server is not None:
            server.emit_signal(signal, json.dumps(payload, ensure_ascii=False))

    def guidance(self, payload):
        self._payload("set_route_guidance", "routeGuidanceChanged", payload)

    def history(self, payload):
        self._payload("set_route_history", "routeHistoryChanged", payload)

    def status(self, success, message):
        dock = self.get_dock()
        if dock is not None:
            dock.set_route_status(success, message)
        server = self.get_external()
        if server is not None:
            server.emit_signal("routeStatusChanged", bool(success), str(message))

    def load_input(self, payload):
        encoded = json.dumps(payload, ensure_ascii=False)
        dock = self.get_dock()
        if dock is not None and dock.web_view is not None:
            dock.web_view.page().runJavaScript(
                f"window.loadRouteHistoryInput({encoded});"
            )
        server = self.get_external()
        if server is not None:
            server.emit_signal("loadRouteHistoryInput", encoded)

    def reset_project(self, epoch):
        dock = self.get_dock()
        if dock is not None:
            dock.reset_project(epoch)
        server = self.get_external()
        if server is not None:
            server.emit_signal("projectReset", epoch)

    @staticmethod
    def seed_external(server, guidance, history, status):
        """Initialize a new server without replaying commands to an existing dock."""
        server.emit_signal("routeGuidanceChanged", json.dumps(guidance, ensure_ascii=False))
        server.emit_signal("routeHistoryChanged", json.dumps(history, ensure_ascii=False))
        if status is not None:
            server.emit_signal("routeStatusChanged", *status)
