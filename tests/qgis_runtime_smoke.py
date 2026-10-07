"""Small runtime smoke test executed by the Python bundled with QGIS."""

import json
import math
import sys
import traceback
from pathlib import Path
from urllib.request import urlopen
from unittest.mock import patch


def run(repo_root):
    sys.path.insert(0, str(repo_root))

    from qgis.core import (
        QgsApplication,
        QgsCoordinateReferenceSystem,
        QgsPointXY,
        QgsProject,
        Qgis,
    )
    from qgis.gui import QgsMapCanvas

    # QGIS imports WebEngine before creating its application object (or sets
    # AA_ShareOpenGLContexts). Mirror that order in this standalone harness.
    from kakao_qgis_bridge import classFactory
    from kakao_qgis_bridge.dock_widget import (
        WEB_RUNTIME_IMPORT_ERRORS,
        QWebChannel,
        QWebEngineView,
    )
    from kakao_qgis_bridge.external_bridge import KakaoExternalBridgeServer

    app = QgsApplication([], False)
    app.initQgis()

    bridge_server = None
    plugin = None
    try:
        class FakeMessageBar:
            def pushInfo(self, *_args):
                pass

            def pushSuccess(self, *_args):
                pass

            def pushWarning(self, *_args):
                pass

        class FakeIface:
            def __init__(self):
                self.canvas = QgsMapCanvas()
                self.canvas.setDestinationCrs(
                    QgsCoordinateReferenceSystem("EPSG:3857")
                )
                self.messages = FakeMessageBar()

            def mapCanvas(self):
                return self.canvas

            def mainWindow(self):
                return None

            def messageBar(self):
                return self.messages

            def removeDockWidget(self, _dock):
                pass

        iface = FakeIface()
        plugin = classFactory(iface)

        key_errors = []
        plugin.mobility_client.failed.connect(key_errors.append)
        plugin.mobility_client.request_route("잘못된 키", None)
        plugin.mobility_client.failed.disconnect(key_errors.append)
        if len(key_errors) != 1 or plugin.mobility_client._reply is not None:
            raise RuntimeError("invalid REST key did not fail before network dispatch")

        lon, lat = plugin._to_epsg_4326(
            QgsPointXY(14_131_740.0, 4_510_736.0)
        )
        if not all(math.isfinite(value) for value in (lon, lat)):
            raise RuntimeError("coordinate transformation returned non-finite values")

        plugin._set_route_point("origin", 126.9784, 37.5667)
        if plugin.route_points_layer.featureCount() != 1:
            raise RuntimeError("route point layer did not receive one feature")

        def point_roles():
            return [category.value() for category in plugin.route_points_layer.renderer().categories()]

        if point_roles() != ["origin"]:
            raise RuntimeError("empty destination/waypoint legend displayed")
        plugin._set_route_point("destination", 127.01, 37.58)
        if point_roles() != ["origin", "destination"]:
            raise RuntimeError("empty waypoint legend displayed")
        plugin._set_route_point("waypoint:1", 127.0, 37.57)
        plugin._set_route_point("waypoint:2", 127.002, 37.572)
        renderer = plugin.route_points_layer.renderer()
        renderer.updateCategoryRenderState(2, False)
        renderer.updateCategoryLabel(2, "경유지 사용자 표시")
        plugin._clear_route_point("waypoint:1")
        if point_roles() != ["origin", "destination", "waypoint"]:
            raise RuntimeError("legend disappeared while a waypoint remained")
        plugin._clear_route_point("waypoint:2")
        if point_roles() != ["origin", "destination"]:
            raise RuntimeError("removed waypoint legend remained")
        plugin._set_route_point("waypoint:3", 127.004, 37.574)
        restored = plugin.route_points_layer.renderer().categories()[2]
        if restored.renderState() or restored.label() != "경유지 사용자 표시":
            raise RuntimeError("waypoint category edits lost when restored")
        plugin._clear_route_points()
        if point_roles() or plugin.route_points_layer.featureCount():
            raise RuntimeError("cleared point legend remained")
        plugin._set_route_point("origin", 126.9784, 37.5667)

        plugin._create_route_layer(
            [QgsPointXY(126.9784, 37.5667), QgsPointXY(127.01, 37.58)],
            3_500,
            600,
            2,
            "10분 · 3.5 km",
            "RECOMMEND",
            0,
            [],
            {"car_type": 1, "car_fuel": "GASOLINE", "car_hipass": False},
        )
        if plugin.route_layer.featureCount() != 1:
            raise RuntimeError("route layer did not receive one feature")

        route_points = [
            QgsPointXY(126.9784, 37.5667),
            QgsPointXY(127.01, 37.58),
        ]
        plugin._append_route_history(
            history_id="history-smoke",
            route_id="route-smoke",
            searched_at="2026-01-01T00:00:00+09:00",
            points=route_points,
            origin=(126.9784, 37.5667),
            destination=(127.01, 37.58),
            origin_label="origin",
            destination_label="destination",
            waypoints=[],
            distance=3_500,
            duration=600,
            guidance_count=0,
            result_summary="10분 · 3.5 km",
            priority="RECOMMEND",
            avoid_options=[],
            vehicle_options={
                "car_type": 1,
                "car_fuel": "GASOLINE",
                "car_hipass": False,
            },
            guides=[],
        )
        if plugin.route_history_layer.featureCount() != 1:
            raise RuntimeError("history repository did not receive one feature")

        bridge_server = KakaoExternalBridgeServer(port=0)
        viewer_url = bridge_server.start()
        with urlopen(viewer_url, timeout=3) as response:
            viewer_loaded = response.status == 200 and b"bridgeToken" in response.read()
        if not viewer_loaded:
            raise RuntimeError("authenticated external viewer did not load")

        # Exercise the occupied-port fallback in the actual QGIS Python runtime.
        preferred_port = int(bridge_server.origin.rsplit(":", 1)[1])
        second_server = KakaoExternalBridgeServer(port=preferred_port, fallback_ports=(0,))
        try:
            second_url = second_server.start()
            if second_server.origin == bridge_server.origin:
                raise RuntimeError("second bridge reused the occupied port")
            with urlopen(second_url, timeout=3) as response:
                if response.status != 200:
                    raise RuntimeError("fallback viewer did not load")
        finally:
            second_server.stop()

        # Restore a route created before the bridge started, and verify that
        # reverse movement reaches another viewer without a 600 ms blackout.
        plugin._set_route_guidance({"history_id": "history-smoke", "path": [
            {"lon": 126.9784, "lat": 37.5667}, {"lon": 127.01, "lat": 37.58},
        ], "guides": []})
        with patch("kakao_qgis_bridge.plugin.KakaoExternalBridgeServer", return_value=bridge_server):
            plugin._ensure_external_bridge()
        state = bridge_server.snapshot()
        if "history-smoke" not in state["signals"]["routeGuidanceChanged"]["args"][0]:
            raise RuntimeError("existing route was not seeded into bridge snapshot")
        if "history-smoke" not in state["signals"]["routeHistoryChanged"]["args"][0]:
            raise RuntimeError("existing history was not seeded into bridge snapshot")

        class FakeDock:
            def __init__(self):
                self.centers = []
                self.visible = True

            def isVisible(self):
                return self.visible

            def set_center(self, lon, lat):
                self.centers.append((lon, lat))

            def hide(self):
                self.visible = False

        dock = FakeDock()
        plugin.dock = dock
        try:
            plugin.sync_controller.activate()
            plugin._handle_viewer_moved(127.0, 37.6, source="tab-a")
            if not dock.centers or bridge_server.snapshot()["center"]["source"] != "tab-a":
                raise RuntimeError("reverse movement did not reach other viewers")
            if plugin.sync_controller.sync_timer.isActive():
                raise RuntimeError("programmatic canvas echo was not suppressed")
            current = iface.canvas.center()
            iface.canvas.setCenter(QgsPointXY(current.x() + 1000, current.y() + 1000))
            if not plugin.sync_controller.sync_timer.isActive():
                raise RuntimeError("immediate user movement was suppressed")
            plugin.sync_controller.sync_timer.stop()
            plugin._sync_canvas_center()
            if bridge_server.snapshot()["center"]["source"] is not None:
                raise RuntimeError("QGIS movement retained a stale viewer source")
            plugin._hide_dock()
            if not plugin.sync_controller.connected:
                raise RuntimeError("hiding dock disconnected active external viewer")
        finally:
            plugin.dock = None

        runtime_mode = (
            "webengine"
            if QWebEngineView is not None and QWebChannel is not None
            else "external-browser"
        )

        return {
            "qgis_version": Qgis.QGIS_VERSION,
            "plugin_class": type(plugin).__name__,
            "runtime_mode": runtime_mode,
            "web_runtime_import_errors": WEB_RUNTIME_IMPORT_ERRORS,
            "coordinate_transform": [round(lon, 6), round(lat, 6)],
            "route_point_features": plugin.route_points_layer.featureCount(),
            "route_point_legend": "only roles with actual features",
            "route_features": plugin.route_layer.featureCount(),
            "history_features": plugin.route_history_layer.featureCount(),
            "external_bridge": "ok",
            "bridge_port_fallback": "occupied port avoided",
            "invalid_rest_key": "rejected",
            "reverse_sync": "echo suppressed, immediate movement forwarded",
            "bridge_snapshot": "existing route and history restored",
            "project_layer_count": len(QgsProject.instance().mapLayers()),
        }
    finally:
        if bridge_server is not None:
            bridge_server.stop()
        if plugin is not None:
            plugin.unload()
        app.processEvents()
        app.exitQgis()


if __name__ == "__main__":
    try:
        root = Path(sys.argv[1]).resolve()
        result = run(root)
        print("SMOKE_RESULT=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
    except Exception:
        traceback.print_exc()
        raise
