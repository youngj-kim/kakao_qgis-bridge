"""Capture/compare actual QGIS styles before and after responsibility moves."""
import hashlib
import json
import sys
from pathlib import Path


def run(root, record=False):
    sys.path.insert(0, str(root))
    from qgis.core import Qgis, QgsApplication, QgsProject
    from kakao_qgis_bridge.plugin import KakaoQgisBridgePlugin
    app = QgsApplication([], False)
    app.initQgis()
    plugin = KakaoQgisBridgePlugin(None)

    def symbol(value):
        layers = []
        for index in range(value.symbolLayerCount()):
            layer = value.symbolLayer(index)
            properties = dict(layer.properties())
            if "name" in properties and properties["name"].startswith("base64:"):
                properties["name"] = "sha256:" + hashlib.sha256(properties["name"].encode()).hexdigest()
            elif "name" in properties and properties["name"].endswith("roadview_radar.svg"):
                properties["name"] = "roadview_radar.svg"
            layers.append(dict(type=layer.layerType(), properties=properties))
        return dict(layers=layers, color=value.color().name(),
                    angle_field=value.dataDefinedAngle().field() if hasattr(value, "dataDefinedAngle") else "")

    def renderer(value):
        return dict(attribute=value.classAttribute(), categories=[
            dict(value=c.value(), label=c.label(), visible=c.renderState(), symbol=symbol(c.symbol()))
            for c in value.categories()])

    try:
        plugin._ensure_route_points_layer()
        roadview = plugin._ensure_roadview_layer()
        styles = dict(route=symbol(plugin._route_line_symbol()),
                      guidance=renderer(plugin._route_guidance_renderer()),
                      gpx=renderer(plugin._gpx_waypoint_renderer()),
                      pin=symbol(plugin._route_pin_symbol("route_origin_pin.svg")),
                      point_categories=[dict(value=c.value(), label=c.label(), symbol=symbol(c.symbol()))
                                        for c in plugin._route_point_categories.values()],
                      initial_point_legend=renderer(plugin.route_points_layer.renderer()),
                      roadview=symbol(roadview.renderer().symbol()))
        path = root / "tests" / "fixtures" / f"qgis{Qgis.QGIS_VERSION.split('.')[0]}-styles.json"
        if record:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(styles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            assert styles == json.loads(path.read_text(encoding="utf-8")), "Styles changed from captured baseline"
        # Mutating one returned object must not affect the next caller.
        factories = [plugin._route_line_symbol, lambda: plugin._route_pin_symbol("route_origin_pin.svg"),
                     lambda: plugin._guidance_symbol("guidance_left.svg")]
        for make in factories:
            first, second = make(), make()
            previous = symbol(second)
            first.symbolLayer(0).setEnabled(False)
            assert second.symbolLayer(0).enabled() and symbol(second) == previous
        for make in (plugin._route_guidance_renderer, plugin._gpx_waypoint_renderer):
            first, second = make(), make()
            previous = renderer(second)
            first.deleteAllCategories()
            assert renderer(second) == previous
        if not record:
            from kakao_qgis_bridge.style_factory import StyleFactory
            factory = StyleFactory()
            assert symbol(factory.route_line_symbol()) == styles["route"]
            assert renderer(factory.route_guidance_renderer()) == styles["guidance"]
            assert renderer(factory.gpx_waypoint_renderer()) == styles["gpx"]
            assert symbol(factory.roadview_symbol()) == styles["roadview"]
        return dict(status="ok", qgis=Qgis.QGIS_VERSION, baseline_recorded=record,
                    checks=["line, pins, guidance, GPX, radar properties", "labels, categories, empty legend",
                            "SVG content and anchors", "fresh symbol/renderer ownership"])
    finally:
        plugin._remove_roadview_layer()
        plugin._remove_route_points_layer()
        QgsProject.instance().removeAllMapLayers()
        app.exitQgis()


if __name__ == "__main__":
    print("STYLE_RESULT=" + json.dumps(run(Path(sys.argv[1]).resolve(), "--record" in sys.argv), ensure_ascii=False))
