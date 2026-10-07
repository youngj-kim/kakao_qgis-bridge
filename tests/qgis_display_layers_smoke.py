"""Compare display data and exercise layer ownership/lifecycle in real QGIS."""
import json
import sys
from pathlib import Path


def run(root, record=False):
    sys.path.insert(0, str(root))
    from qgis.core import (Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsProject,
                           QgsPointXY, QgsVectorLayer)
    from qgis.gui import QgsMapCanvas
    from kakao_qgis_bridge.plugin import KakaoQgisBridgePlugin
    app = QgsApplication([], False)
    app.initQgis()

    class Iface:
        def __init__(self):
            self.canvas = QgsMapCanvas()
            self.canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))

        def mapCanvas(self):
            return self.canvas

    iface = Iface()
    plugin = KakaoQgisBridgePlugin(iface)
    project = QgsProject.instance()
    checks = []
    points = [QgsPointXY(127.001234567, 37.501234567), QgsPointXY(127.004567891, 37.504567891)]
    guides = [dict(route_id="route", sequence=seq, section_no=1, guide_type=2,
                   category="right", guidance="안내", name="도로", distance_m=12, duration_s=3,
                   cumulative_distance_m=12 * seq, cumulative_duration_s=3 * seq,
                   road_index=-1 if seq == 2 else 0, longitude=127.002345678 + seq / 1000,
                   latitude=37.502345678) for seq in (1, 2)]

    def route():
        plugin._create_route_layer(points, 100, 20, 2, "경로", "RECOMMEND", 1, ["toll"],
                                   dict(car_type=1, car_fuel="GASOLINE", car_hipass=True))

    def snapshot(layer):
        return dict(name=layer.name(), crs=layer.crs().authid(), skip=layer.customProperty("skipMemoryLayersCheck"),
                    fields=[(f.name(), f.typeName(), f.length(), f.precision()) for f in layer.fields()],
                    features=[dict(geometry=f.geometry().asWkt(10), attributes=f.attributes()) for f in layer.getFeatures()])

    try:
        # A user's same-name layer must survive all plugin-owned removals.
        unrelated = QgsVectorLayer("Point?crs=EPSG:4326", "Kakao Mobility Route", "memory")
        project.addMapLayer(unrelated)
        unrelated_id = unrelated.id()
        route()
        plugin._create_route_guidance_layer(guides)
        plugin._update_roadview_layer(127.001234567, 37.501234567, 123, -5, 1, "pano")
        plugin._set_route_point("origin", 127.001234567, 37.501234567)
        plugin._set_route_point("destination", 127.004567891, 37.504567891)
        plugin._set_route_point("waypoint:0", 127.003456789, 37.503456789)
        data = {name: snapshot(getattr(plugin, name)) for name in
                ("route_layer", "route_guidance_layer", "roadview_layer", "route_points_layer")}
        data["canvas_extent"] = iface.canvas.extent().toString(6)
        baseline = root / "tests" / "fixtures" / f"qgis{Qgis.QGIS_VERSION.split('.')[0]}-display.json"
        if record:
            baseline.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            # JSON represents field tuples as lists.
            assert json.loads(json.dumps(data)) == json.loads(baseline.read_text(encoding="utf-8"))
        checks.append("display names, fields, attributes, geometry, CRS, canvas extent unchanged")
        point_id = plugin.route_point_feature_ids["origin"]
        radar_id = plugin.roadview_feature_id
        plugin._set_route_point("origin", 127.1, 37.6)
        plugin._update_roadview_layer(127.1, 37.6, 90, 0, 2, "next")
        assert plugin.route_point_feature_ids["origin"] == point_id and plugin.roadview_feature_id == radar_id
        assert plugin.route_points_layer.featureCount() == 3 and plugin.roadview_layer.featureCount() == 1
        plugin.route_points_layer.dataProvider().deleteFeatures([point_id])
        plugin.roadview_layer.dataProvider().deleteFeatures([radar_id])
        plugin._set_route_point("origin", 127.2, 37.7)
        plugin._update_roadview_layer(127.2, 37.7, 45, 0, 1, "rebuilt")
        assert plugin.route_points_layer.featureCount() == 3 and plugin.roadview_layer.featureCount() == 1
        checks.append("existing feature updates and manually deleted feature recreation")
        old_route = plugin.route_layer.id()
        route()
        assert project.mapLayer(old_route) is None and len(project.mapLayers()) == 5
        plugin._create_route_guidance_layer([])
        assert plugin.route_guidance_layer is None and plugin.route_guidance_feature_ids == {}
        plugin._create_route_guidance_layer(guides)
        assert len(project.mapLayers()) == 5
        plugin._focus_route_guidance(2, 127, 37)
        assert plugin.route_guidance_layer.selectedFeatureIds() == [plugin.route_guidance_feature_ids[2]]
        checks.append("route replacement, empty guidance, selection and no duplicate layers")
        for name in ("roadview_layer", "route_points_layer", "route_guidance_layer", "route_layer"):
            project.removeMapLayer(getattr(plugin, name).id())
        plugin._update_roadview_layer(127, 37, 0, 0, 1, "new")
        plugin._set_route_point("origin", 127, 37)
        plugin._focus_route_guidance(1, 127, 37)
        assert plugin.route_guidance_layer is None and plugin.route_guidance_feature_ids == {}
        route()
        plugin._create_route_guidance_layer(guides)
        assert project.mapLayer(unrelated_id) is not None and len(project.mapLayers()) == 5
        checks.append("manually removed layers safely recreated; unrelated same-name layer retained")
        plugin.history_repository.ensure_layers()
        history = plugin.history_repository.route_layer
        plugin.active_route_history_id = "retained"
        project.clear()
        # Preserve session history policy: display refactoring does not discard it.
        assert plugin.history_repository.route_layer is history and plugin.active_route_history_id == "retained"
        plugin._set_route_point("origin", 127, 37)
        plugin._update_roadview_layer(127, 37, 0, 0, 1, "after-clear")
        route()
        plugin._create_route_guidance_layer(guides)
        assert len(project.mapLayers()) == 4
        checks.append("project clear, lazy display recreation, internal history policy retained")
        unrelated = QgsVectorLayer("Point?crs=EPSG:4326", "GPX/user layer", "memory")
        project.addMapLayer(unrelated)
        unrelated_id = unrelated.id()
        plugin.unload()
        assert set(project.mapLayers()) == {unrelated_id}
        assert all(getattr(plugin, name) is None for name in
                   ("roadview_layer", "route_layer", "route_guidance_layer", "route_points_layer"))
        assert plugin.route_point_feature_ids == {} and plugin.route_guidance_feature_ids == {}
        plugin.unload()
        assert set(project.mapLayers()) == {unrelated_id}
        checks.append("unload removes only owned display layers; repeated cleanup safe")
        return dict(status="ok", qgis=Qgis.QGIS_VERSION, baseline_recorded=record, checks=checks)
    finally:
        plugin.unload()
        project.removeAllMapLayers()
        app.exitQgis()


if __name__ == "__main__":
    print("DISPLAY_RESULT=" + json.dumps(run(Path(sys.argv[1]).resolve(), "--record" in sys.argv), ensure_ascii=False))
