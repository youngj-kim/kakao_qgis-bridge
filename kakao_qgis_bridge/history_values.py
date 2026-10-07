"""Shared history value conversions used by viewer restoration and export."""
import json


def safe_number(value):
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def safe_float(value):
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def route_points_from_geometry(geometry):
    if geometry is None or geometry.isEmpty():
        return []
    if geometry.isMultipart():
        parts = geometry.asMultiPolyline()
        return parts[0] if parts else []
    return geometry.asPolyline()


def waypoints_from_history(route_feature):
    try:
        waypoints = json.loads(str(route_feature["waypoints_json"] or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return waypoints if isinstance(waypoints, list) else []
