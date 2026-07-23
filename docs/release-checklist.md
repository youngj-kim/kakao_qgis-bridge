# QGIS Plugin Repository Release Checklist

Use this checklist before uploading `Kakao QGIS Bridge` to the official QGIS
plugin repository.

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

## Package

- [x] ZIP contains a single top-level `kakao_qgis_bridge/` folder.
- [x] ZIP excludes `.git`, `.agents`, `.codex`, `__pycache__`, `.pytest_cache`, and local settings.
- [x] ZIP excludes `kakao_qgis_bridge/settings.json`.
- [x] ZIP excludes generated test/output files.
- [x] ZIP size is below the QGIS repository package limit.
- [ ] Source code in the ZIP matches the public GitHub repository.

## Upload

- [ ] Log in to https://plugins.qgis.org/ with an OSGeo ID.
- [ ] Upload the plugin ZIP using "Share a plugin".
- [ ] Check the repository page for validation warnings.
- [ ] Watch the account email or plugin page for approval/rejection feedback.
