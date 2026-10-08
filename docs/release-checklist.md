# GitHub and ZIP Distribution Checklist

Distribution scope (2026-10-08): GitHub source and ZIP files. The user has
excluded uploading to the official QGIS plugin repository. Historical upload
items below are retained as past planning, not current tasks.

## 1.2.0 preparation status — 2026-10-07

The checklist below this section records earlier release work. Its checked
boxes are not evidence that all checks were repeated on the 1.2.0 ZIP.

- [x] Update version, metadata changelog and root CHANGELOG.md to 1.2.0.
- [x] Add standalone setup instructions inside the plugin ZIP and update about.
- [x] Document both SDK domains, bridge fallback and the scope of KAKAO_MAP_BASE_URL.
- [x] Document center-only sync, memory history, SHP loss and credential limits.
- [x] Record actual runtime coverage: Windows QGIS 3.44.14 and 4.2.2.
- [ ] Run the declared minimum QGIS 3.34 against this build. A leftover 3.34.12
  directory has no Python/QGIS runtime and cannot provide execution evidence.
  Keep the declared minimum unchanged; this does not establish incompatibility.
- [ ] Confirm the Kakao SDK embedding terms and quota suitability.
- [ ] Perform the final installed 1.2.0 SDK/browser check. Earlier user checks
  and runtime regressions are recorded in refactoring-progress.md.
- [ ] Commit/push the 1.2.0 metadata and documentation to GitHub and confirm
  the CI result. Earlier refactoring commit: 3d9bc21 (CI passed).
- [ ] Create a GitHub release/tag with a ZIP if a release is requested.

Official QGIS plugin repository upload is outside the distribution scope.

Candidate package: `dist/kakao_qgis_bridge-1.2.0.zip`.
Package verification is recorded in refactoring-progress.md. Until the open
items are resolved, treat it as a local release candidate.

## Earlier release checklist (historical)

## Repository

- [x] Confirm the GitHub repository is public.
- [x] Confirm `metadata.txt` links are reachable:
  - [x] `homepage`
  - [x] `repository`
  - [x] `tracker`
- [x] Confirm `README.md` explains installation, API keys, usage, and limits.
- [x] Confirm `LICENSE` is present in the repository root.
- [x] Confirm `kakao_qgis_bridge/LICENSE` is included in the plugin package.
- [x] Confirm no API keys, account details, or local user paths are committed.

## Metadata

- [x] `name` is final.
- [x] `version` is updated.
- [x] `qgisMinimumVersion` is correct.
- [x] `qgisMaximumVersion` is correct.
- [x] `description` is short and accurate.
- [x] `about` mentions Kakao API requirements and restrictions.
- [x] `license=GPL-2.0-or-later` is present.
- [x] `experimental=True` or `experimental=False` is intentional.

## Screenshots and Docs

- [x] Add screenshots under `docs/screenshots/`.
- [x] Review screenshots for API keys, account information, and sensitive locations.
- [x] Add representative screenshots to `README.md`.
- [x] Move detailed walkthrough screenshots to `docs/usage.md` if README becomes too long.

## Functional Smoke Test

- [x] Install/use in the active QGIS development profile.
- [x] Enable the plugin from QGIS Plugin Manager.
- [x] Open `Kakao Map / Roadview`.
- [x] Set Kakao JavaScript API key.
- [x] Confirm QGIS canvas center syncs to Kakao Map and Roadview.
- [x] Confirm Kakao Map drag syncs back to QGIS.
- [x] Confirm Roadview movement updates the QGIS roadview position layer.
- [x] Confirm Local place/address search works.
- [x] Set Kakao REST API key.
- [x] Create a route with origin and destination.
- [x] Create a route with at least one waypoint.
- [x] Confirm route, route points, and guidance layers are created.
- [x] Confirm guidance list item selection focuses the matching QGIS feature.
- [x] Save route history to GeoPackage.
- [x] Load route history from GeoPackage.
- [x] Export route history to GeoJSON.
- [x] Export route history to Shapefile.
- [x] Export route history to GPX.
- [x] Load GPX with sidecar QML styles.
- [x] Test external browser integration mode when available.
- [ ] Open the external browser viewer from the plugin menu while the Dock is
  closed and confirm QGIS-to-browser synchronization remains active.
- [ ] Confirm an external bridge API request without the current session token
  is rejected and does not change QGIS state.

## Automated Checks

- [x] Run `python -m compileall -q kakao_qgis_bridge tests`.
- [x] Run `python -m unittest discover -s tests -v`.
- [x] Confirm the inline viewer JavaScript parses without syntax errors.
- [x] Run `tests/qgis_runtime_smoke.py` with the bundled Python runtimes from
  QGIS 3.44 and QGIS 4.2.
- [x] Create and show the real Dock widget in QGIS 3.44 and in a full QGIS 4.2
  desktop application instance.
- [x] Restart QGIS 4.2 with the installed test build and confirm the plugin
  operates normally in the user's desktop session.
- [x] Restart QGIS 3.44 with the installed test build and confirm the external
  browser integration operates normally in the user's desktop session.
- [x] Run the automated checks in CI on every pull request and release tag.

## Package

- [x] ZIP contains a single top-level `kakao_qgis_bridge/` folder.
- [x] ZIP excludes `.git`, `.agents`, `.codex`, `__pycache__`, `.pytest_cache`, and local settings.
- [x] ZIP excludes `kakao_qgis_bridge/settings.json`.
- [x] ZIP excludes generated test/output files.
- [x] ZIP size is below the QGIS repository package limit.
- [x] Source code in the ZIP matches the public GitHub repository.

## Upload

- [ ] Log in to https://plugins.qgis.org/ with an OSGeo ID.
- [ ] Upload the plugin ZIP using "Share a plugin".
- [ ] Check the repository page for validation warnings.
- [ ] Watch the account email or plugin page for approval/rejection feedback.
