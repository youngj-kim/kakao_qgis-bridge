# Screenshot Capture List

Use this list when capturing screenshots for README and QGIS plugin repository
release documentation.

## Capture Rules

- Use PNG format.
- Save all files under `docs/screenshots/`.
- Keep filenames exactly as listed below unless the README links are updated too.
- Hide or blur API keys, account names, local file paths, and sensitive locations.
- Prefer the same QGIS window size for related screenshots.
- Keep the Layers panel visible when the screenshot demonstrates generated QGIS layers.
- Use a neutral sample route and location that is safe to publish.

## Required Screenshots

- [ ] `01-plugin-menu.png`
  - Show: QGIS `Plugins > Kakao QGIS Bridge` menu.
  - Include: `Kakao Map / Roadview`, API key settings, route history load/save/export actions.
  - Purpose: Proves plugin menu registration and available actions.

- [ ] `02-dock-basic.png`
  - Show: Kakao Map / Roadview dock opened in QGIS.
  - Include: search input, layout selector, map, roadview, route input area.
  - Purpose: Main product screenshot for README.

- [ ] `03-position-sync.png`
  - Show: QGIS canvas and Kakao viewer synchronized to the same area.
  - Include: QGIS map canvas, dock status text, Kakao map marker or roadview.
  - Purpose: Demonstrates QGIS to Kakao synchronization.

- [x] `04-local-search_search_input.png`
  - Show: place/address search result list.
  - Include: query text, search results, selected/target location if possible.
  - Purpose: Documents Kakao Local search.

- [ ] `05-roadview-layer.png`
  - Show: `Kakao Roadview Position` layer in QGIS.
  - Include: Layers panel, roadview direction marker, attribute table or visible marker.
  - Purpose: Demonstrates roadview position/direction feedback to QGIS.

- [ ] `06-route-input.png`
  - Show: route form before creating a route.
  - Include: origin, destination, at least one waypoint, priority, avoid options, vehicle options.
  - Purpose: Documents route search controls.

- [ ] `07-route-result.png`
  - Show: route result after `경로 생성`.
  - Include: `Kakao Mobility Route`, `Kakao Route Points`, `Kakao Route Guidance` layers, route line, pins.
  - Purpose: Main route feature screenshot.

- [ ] `08-guidance-selection.png`
  - Show: one guidance item selected.
  - Include: Dock guidance list, selected item, QGIS selected feature or focused map point.
  - Purpose: Demonstrates turn-by-turn guidance interaction.

- [ ] `09-route-history.png`
  - Show: route history tab.
  - Include: history list, selected history item, load/export/delete actions.
  - Purpose: Documents session history workflow.

- [ ] `10-external-browser.png`
  - Show: external browser integration mode.
  - Include: QGIS window and external Kakao Viewer browser if possible.
  - Purpose: Documents QGIS 3 / external viewer fallback.

## Optional Screenshots

- [ ] `11-export-files.png`
  - Show: exported files or reloaded export layers.
  - Include: GeoPackage, GeoJSON, Shapefile, or GPX outputs as relevant.
  - Purpose: Demonstrates export workflow.

- [x] `12-gpx-load-menu.png`
  - Show: GPX styled load menu action.
  - Include: `플러그인 > Kakao QGIS Bridge > GPX 스타일 적용해서 불러오기...`.
  - Purpose: Documents the menu entry for GPX style restoration.

- [x] `12-gpx-load-output.png`
  - Show: GPX loaded with sidecar QML styles.
  - Include: `tracks`, `routes`, `waypoints` layers with styles applied.
  - Purpose: Documents GPX style restore workflow.

- [ ] `13-layout-map-left.png`
  - Show: map-left / roadview-right layout.
  - Include: layout selector value and split view.
  - Purpose: Optional responsive layout proof.

- [ ] `14-fullscreen.png`
  - Show: fullscreen viewer.
  - Include: map, roadview, and controls in fullscreen mode.
  - Purpose: Optional fullscreen feature proof.

- [ ] `15-api-key-dialog.png`
  - Show: API key setting dialog.
  - Include: dialog title only; hide or leave key field empty.
  - Purpose: Optional setup documentation.

## README Recommendation

Use these screenshots in README first:

- `02-dock-basic.png`
- `04-local-search_search_input.png`
- `07-route-result.png`
- `08-guidance-selection.png`
- `09-route-history.png`
- `10-external-browser.png`

Keep the remaining screenshots for `docs/usage.md` or release notes if README
becomes too long.
