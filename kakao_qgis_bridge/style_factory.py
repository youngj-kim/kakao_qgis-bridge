"""Fresh QGIS symbols and renderers, independent of plugin UI and layers."""
from base64 import b64encode
from functools import lru_cache
from pathlib import Path

from qgis.core import (Qgis, QgsCategorizedSymbolRenderer, QgsLineSymbol,
                       QgsMarkerSymbol, QgsProperty, QgsRendererCategory,
                       QgsSvgMarkerSymbolLayer)

PLUGIN_DIR = Path(__file__).resolve().parent


class StyleFactory:
    def gpx_waypoint_renderer(self):
        return QgsCategorizedSymbolRenderer(
            "type",
            [
                QgsRendererCategory(
                    "origin",
                    self.route_pin_symbol("route_origin_pin.svg", 7.5),
                    "출발지",
                ),
                QgsRendererCategory(
                    "destination",
                    self.route_pin_symbol("route_destination_pin.svg", 7.5),
                    "도착지",
                ),
                QgsRendererCategory(
                    "waypoint",
                    self.route_pin_symbol("route_waypoint_pin.svg", 7.5),
                    "경유지",
                ),
                QgsRendererCategory(
                    "guidance:straight",
                    self.guidance_symbol("guidance_straight.svg"),
                    "직진",
                ),
                QgsRendererCategory(
                    "guidance:left",
                    self.guidance_symbol("guidance_left.svg"),
                    "좌회전",
                ),
                QgsRendererCategory(
                    "guidance:right",
                    self.guidance_symbol("guidance_right.svg"),
                    "우회전",
                ),
                QgsRendererCategory(
                    "guidance:uturn",
                    self.guidance_symbol("guidance_uturn.svg"),
                    "유턴",
                ),
                QgsRendererCategory(
                    "guidance:roundabout",
                    self.guidance_symbol("guidance_roundabout.svg"),
                    "회전교차로",
                ),
                QgsRendererCategory(
                    "guidance:transition",
                    self.guidance_symbol("guidance_transition.svg"),
                    "진출입",
                ),
                QgsRendererCategory(
                    "guidance:other",
                    self.guidance_symbol("guidance_other.svg"),
                    "기타 안내",
                ),
            ],
        )

    @staticmethod
    def route_line_symbol():
        return QgsLineSymbol.createSimple(
            {
                "line_color": "#1976d2",
                "line_width": "1.4",
            }
        )

    def route_guidance_renderer(self):
        return QgsCategorizedSymbolRenderer(
            "category",
            [
                QgsRendererCategory(
                    "start",
                    self.route_pin_symbol("route_origin_pin.svg", 7.5),
                    "출발",
                ),
                QgsRendererCategory(
                    "destination",
                    self.route_pin_symbol(
                        "route_destination_pin.svg",
                        7.5,
                    ),
                    "도착",
                ),
                QgsRendererCategory(
                    "waypoint",
                    self.route_pin_symbol("route_waypoint_pin.svg", 7.5),
                    "경유지",
                ),
                QgsRendererCategory(
                    "straight",
                    self.guidance_symbol("guidance_straight.svg"),
                    "직진",
                ),
                QgsRendererCategory(
                    "left",
                    self.guidance_symbol("guidance_left.svg"),
                    "좌회전",
                ),
                QgsRendererCategory(
                    "right",
                    self.guidance_symbol("guidance_right.svg"),
                    "우회전",
                ),
                QgsRendererCategory(
                    "uturn",
                    self.guidance_symbol("guidance_uturn.svg"),
                    "유턴",
                ),
                QgsRendererCategory(
                    "roundabout",
                    self.guidance_symbol("guidance_roundabout.svg"),
                    "회전교차로",
                ),
                QgsRendererCategory(
                    "transition",
                    self.guidance_symbol("guidance_transition.svg"),
                    "진출입",
                ),
                QgsRendererCategory(
                    "other",
                    self.guidance_symbol("guidance_other.svg"),
                    "기타 안내",
                ),
            ],
        )

    @staticmethod
    def guidance_symbol(filename):
        return QgsMarkerSymbol(
            [
                QgsSvgMarkerSymbolLayer(
                    StyleFactory.embedded_svg_path(filename),
                    6.5,
                )
            ]
        )

    @staticmethod
    def route_pin_symbol(filename, size=9.0):
        symbol_layer = QgsSvgMarkerSymbolLayer(
            StyleFactory.embedded_svg_path(filename),
            size,
        )
        vertical_anchor = getattr(Qgis, "VerticalAnchorPoint", None)
        bottom_anchor = getattr(vertical_anchor, "Bottom", None)
        if bottom_anchor is None:
            bottom_anchor = getattr(symbol_layer, "Bottom", None)
        if bottom_anchor is not None:
            symbol_layer.setVerticalAnchorPoint(bottom_anchor)
        return QgsMarkerSymbol([symbol_layer])

    @staticmethod
    @lru_cache(maxsize=None)
    def embedded_svg_path(filename):
        svg_path = PLUGIN_DIR / "web" / filename
        encoded = b64encode(svg_path.read_bytes()).decode("ascii")
        return f"base64:{encoded}"

    def route_point_renderer(self):
        return QgsCategorizedSymbolRenderer("role", [
            QgsRendererCategory("origin", self.route_pin_symbol("route_origin_pin.svg"), "출발지"),
            QgsRendererCategory("destination", self.route_pin_symbol("route_destination_pin.svg"), "도착지"),
            QgsRendererCategory("waypoint", self.route_pin_symbol("route_waypoint_pin.svg"), "경유지"),
        ])

    @staticmethod
    def roadview_symbol():
        svg_path = PLUGIN_DIR / "web" / "roadview_radar.svg"
        symbol = QgsMarkerSymbol([QgsSvgMarkerSymbolLayer(str(svg_path), 24.0)])
        symbol.setDataDefinedAngle(QgsProperty.fromField("pan"))
        return symbol
