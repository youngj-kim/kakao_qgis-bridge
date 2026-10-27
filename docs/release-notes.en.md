# Release notes

[English README](../README.en.md) · [Full changelog (Korean)](../CHANGELOG.md)

These notes summarize the current release and development candidate. Earlier release records remain in the full changelog. Test results below are recorded results from those releases, not checks rerun for this documentation update.

## 1.3.1 — Development candidate (2026-10-27)

- Keep directions and history visible when collapsing explorer search, map settings, and route inputs.
- Collapse or expand the directions/history list independently while retaining its tabs and summary.
- Improve bilingual toggle tooltips, accessibility state, and map/Roadview resizing after collapse changes.
- Recorded verification: 55 viewer JavaScript tests, 2 Python viewer template/structure tests, and JavaScript syntax checks passed. Manual verification in QGIS is pending.

## 1.3 — 2026-10-23

- Add English/Korean switching for main viewer controls and save the language preference, including dynamically generated history controls.
- Compact layout, language, fullscreen, waypoint, and route-option controls to give maps more space.
- Rename the map-center input button to **Here / 현위치**. It uses the Kakao map center, not GPS.
- Include changes since 1.2.1: Roadmap/Aerial/Aerial + labels switching, Roadview road coverage, collapsible explorer/search results, and improved floating/docked size restoration and viewer resizing.
- Store tolls and estimated taxi fares in new route histories and show A/B amounts and B−A differences in GPKG comparison. Preserve missing fares as unknown; do not infer them from existing files.
- Update setup, usage, and release documentation with 17 screenshots and instructions for route reset, history deletion, selected export, restoration, and route/fare comparison.
- Recorded verification: the user confirmed functionality in QGIS 3.44 and rechecked existing functionality in QGIS 4. Package preparation passed 81 Python tests, 64 JavaScript tests, JavaScript syntax checks, and Bandit checks without findings. Declared QGIS 3.34 support remains untested at runtime. Repository approval and remote CI are separate from these local checks.

After installing an update, restart QGIS, close old external viewer tabs, and open a new viewer from the plugin. Register both `http://localhost:8081` and `http://localhost:8082` as SDK domains. Viewer translation excludes SDK place names, QGIS menus/dialogs, and some status messages. History is not saved automatically.
