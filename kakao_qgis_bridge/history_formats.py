"""Shared history file names and full/short field-name mappings."""
from pathlib import Path

HISTORY_SCHEMA_VERSION = 2
ROUTE_HISTORY_LAYER_NAME = "kakao_route_history"
GUIDANCE_HISTORY_LAYER_NAME = "kakao_guidance_history"


def full_history_field_specs(layer_type):
    if layer_type == "route":
        return [
            {"source": "schema_ver", "name": "schema_v"},
            {"source": "history_id", "name": "hist_id"},
            {"source": "route_id", "name": "route_id"},
            {"source": "searched_at", "name": "searched"},
            {"source": "origin_lon", "name": "org_lon"},
            {"source": "origin_lat", "name": "org_lat"},
            {"source": "origin_name", "name": "org_name"},
            {"source": "destination_lon", "name": "dst_lon"},
            {"source": "destination_lat", "name": "dst_lat"},
            {"source": "destination_name", "name": "dst_name"},
            {"source": "waypoints_json", "name": "waypts"},
            {"source": "distance_m", "name": "dist_m"},
            {"source": "duration_s", "name": "dur_s"},
            {"source": "guidance_count", "name": "guide_cnt"},
            {"source": "result_summary", "name": "summary"},
            {"source": "priority", "name": "priority"},
            {"source": "avoid", "name": "avoid"},
            {"source": "car_type", "name": "car_type"},
            {"source": "car_fuel", "name": "car_fuel"},
            {"source": "car_hipass", "name": "car_hipass"},
        ]
    return [
        {"source": "schema_ver", "name": "schema_v"},
        {"source": "history_id", "name": "hist_id"},
        {"source": "route_id", "name": "route_id"},
        {"source": "searched_at", "name": "searched"},
        {"source": "sequence", "name": "seq"},
        {"source": "section_no", "name": "sect_no"},
        {"source": "guide_type", "name": "g_type"},
        {"source": "category", "name": "category"},
        {"source": "guidance", "name": "guidance"},
        {"source": "name", "name": "name"},
        {"source": "distance_m", "name": "dist_m"},
        {"source": "duration_s", "name": "dur_s"},
        {"source": "cum_distance_m", "name": "cum_dist"},
        {"source": "cum_duration_s", "name": "cum_dur"},
        {"source": "road_index", "name": "road_idx"},
        {"source": "longitude", "name": "lon"},
        {"source": "latitude", "name": "lat"},
    ]


def history_value(feature, source_fields, full_name, short_name):
    if full_name in source_fields:
        return feature[full_name]
    if short_name in source_fields:
        return feature[short_name]
    return None


def paired_output_paths(filename, extension):
    selected_path = Path(filename)
    if selected_path.suffix.lower() != extension:
        selected_path = selected_path.with_suffix(extension)

    base_stem = selected_path.stem
    for paired_suffix in ("_routes", "_guidance"):
        if base_stem.lower().endswith(paired_suffix):
            base_stem = base_stem[:-len(paired_suffix)]
            break

    route_path = selected_path.with_name(
        f"{base_stem}_routes{selected_path.suffix}"
    )
    guidance_path = selected_path.with_name(
        f"{base_stem}_guidance{selected_path.suffix}"
    )
    return route_path, guidance_path
