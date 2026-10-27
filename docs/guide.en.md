# Setup and usage

[English README](../README.en.md) · [한국어 설정](setup.md) · [한국어 사용 가이드](usage.md)

This guide describes released version 1.3 and explicitly identifies changes in the 1.3.1 development candidate.

## Installation and API keys

Install the distribution ZIP using QGIS **Manage and Install Plugins → Install from ZIP**. Restart QGIS and enable the plugin. After updating, close old external browser tabs and open a new viewer using the plugin button.

Create an application in [Kakao Developers](https://developers.kakao.com/). In its platform key settings, register both origins below as **JavaScript SDK domains** for the JavaScript key:

```text
http://localhost:8081
http://localhost:8082
```

The JavaScript key is used for maps, Roadview, and place/address search. The REST API key is used for Kakao Mobility route requests. The plugin does not use an admin key. Consult the [official Kakao Maps guide](https://apis.map.kakao.com/web/guide/) for provider setup requirements.

Open **Kakao Map / Roadview** to enter the JavaScript key. Create a route to enter the REST API key. To replace a key, use the corresponding API key settings command under **Plugins → Kakao QGIS Bridge**. Keys are saved in QGIS user settings without encryption; never add real keys to source files or distribution packages.

Environment variables override saved settings: `KAKAO_MAP_JAVASCRIPT_KEY` and `KAKAO_REST_API_KEY`. The JavaScript key can also fall back to the legacy `kakao_qgis_bridge/settings.json`. Restart QGIS after changing environment variables.

## Embedded and external viewers

The plugin uses a dock when Qt WebEngine/WebChannel is available and provides an external browser viewer otherwise. You can also open an external viewer from the embedded viewer.

The external bridge tries port 8081, then 8082 if the first is occupied. This also allows two QGIS sessions to use separate bridge ports. Different ports are different SDK origins, so register both with the same JavaScript key. If both ports are occupied, close an unused bridge session and try again.

`KAKAO_MAP_BASE_URL` changes the embedded viewer's base URL, not external bridge ports. Register any custom embedded origin as an additional SDK domain. The default embedded base URL is `http://localhost:8081/kakao_qgis_bridge/`; it does not require a separate web server.

Old tabs may contain an expired session token and return HTTP 403. Reopen the viewer with the current QGIS plugin button; manually entering its address does not authenticate the session. SDK domain errors and bridge authentication errors have different causes.

## Viewer and search

Use **EN / KR** to switch the main viewer controls. The preference is saved separately in the embedded viewer and external browser when storage is available. SDK place names, QGIS menus/dialogs, and some status messages are outside this translation scope.

Choose a vertical or horizontal layout, drag the divider to resize the map and Roadview, or use fullscreen. Collapsing the explorer preserves inputs and results. In the **1.3.1 development candidate**, explorer collapse hides search/map settings/route inputs while keeping directions/history available; a separate −/+ control collapses the results list while retaining its tabs and summary.

Search for a place or address and select a result to move QGIS, Kakao Map, and Roadview together. Search results can be collapsed and reopened. Map types include Roadmap, Aerial, and Aerial + labels; **Show Roadview roads** toggles capture-road coverage. These options do not change the QGIS basemap.

Map position and zoom synchronize both ways. Zoom-only changes keep the Roadview capture position. Kakao roadmap levels 1–14 and the QGIS scale lock limit zoom matching.

## Driving routes

1. Enter origin and destination as places, addresses, or coordinates, for example `126.9786567,37.566826` (longitude, latitude).
2. Select a search candidate to confirm a location, or use **Here** to use the current Kakao map center. Here does not read GPS location.
3. Add up to five waypoints. Reorder them with the arrows or swap origin and destination.
4. Select Recommended, Fastest, or Shortest, then set avoidance and vehicle options as needed.
5. Select **Create route**. Enter your REST API key if prompted.

QGIS displays temporary `Kakao Mobility Route`, `Kakao Route Points`, and `Kakao Route Guidance` layers. Selecting guidance moves the linked views to that location. Result pins use API guidance coordinates while original input coordinates remain available for editing, repeat searches, and history. Missing waypoint guidance produces no corresponding result pin.

The search × clears the search text and results. The route × clears route inputs and the current route display; session history remains available.

## History and export

Successful routes accumulate in the session's **History** tab. Selecting an entry displays its result; **Load** restores its inputs and options. Use checkboxes and the selected-save action to export multiple entries, or an entry's export action for one route. QGIS plugin menus also export the whole session.

**History is not automatically saved. Export before disabling the plugin or exiting QGIS.** GeoPackage and GeoJSON are recommended for complete attributes. Shapefile can truncate long strings and waypoint JSON. GeoJSON/Shapefile export produces separate route/guidance files and QML styles. GPX export creates tracks, routes, waypoints, and QML sidecars; use the plugin's GPX style-loading command to apply them.

Import GeoPackage or paired route/guidance GeoJSON/Shapefile files through the history import action. Existing session `history_id` values are skipped. GPX is loaded as layers rather than imported as session history. Saving to the same GeoPackage appends new history IDs and preserves other layers.

Deleting an entry or all history requires confirmation and changes the current session, leaving exported source files intact. Deleting the displayed entry also clears its current route/guidance display. Changing QGIS projects resets current inputs, display, and pending requests but keeps session history; select an entry to display it in the new project.

## GPKG route and fare comparison

Open **GPKG 경로 비교...** in the plugin menu and select Kakao/Naver files as A and B. Compare distance, predicted duration, query time, route points, and B−A differences. A is a blue solid line and B an orange dashed line. Comparison leaves source files and session history intact.

Supported route layers are `kakao_route_history` or `naver_route_history` in EPSG:4326 with LineString/MultiLineString geometry. Generic Geometry declarations are unsupported.

New histories store tolls and estimated taxi fares in KRW. Missing fares remain unknown rather than zero. Obtain fares by querying and exporting a new route; the plugin does not reconstruct them from older files. Tolls and taxi estimates are not added together, and estimates do not guarantee actual charges.

## Troubleshooting

- Map missing: check the JavaScript key and registered SDK origins, including both bridge ports.
- Map works but routes fail: check the REST API key, route-service access, and displayed error.
- External tab returns a connection/authentication error: close it and open a fresh viewer from QGIS.
- Both bridge ports occupied: close an unused QGIS bridge session.

For historical Roadview imagery, open the official Kakao Map link provided by the viewer. The plugin API does not provide the historical capture list.
