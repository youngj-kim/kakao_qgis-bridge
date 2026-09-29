"""Small runtime smoke test executed by the Python bundled with QGIS."""

import json
import math
import sys
import traceback
from pathlib import Path
from urllib.request import urlopen


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

        lon, lat = plugin._to_epsg_4326(
            QgsPointXY(14_131_740.0, 4_510_736.0)
        )
        if not all(math.isfinite(value) for value in (lon, lat)):
            raise RuntimeError("coordinate transformation returned non-finite values")

        plugin._set_route_point("origin", 126.9784, 37.5667)
        if plugin.route_points_layer.featureCount() != 1:
            raise RuntimeError("route point layer did not receive one feature")

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
            "route_features": plugin.route_layer.featureCount(),
            "history_features": plugin.route_history_layer.featureCount(),
            "external_bridge": "ok",
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
