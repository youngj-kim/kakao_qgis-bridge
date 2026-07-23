# QGIS Plugin Repository Release Checklist

Use this checklist before uploading `Kakao QGIS Bridge` to the official QGIS
plugin repository.

## Repository

- [ ] Confirm the GitHub repository is public.
- [ ] Confirm `metadata.txt` links are reachable:
  - [ ] `homepage`
  - [ ] `repository`
  - [ ] `tracker`
- [ ] Confirm `README.md` explains installation, API keys, usage, and limits.
- [ ] Confirm `LICENSE` is present in the repository root.
- [ ] Confirm `kakao_qgis_bridge/LICENSE` is included in the plugin package.
- [ ] Confirm no API keys, account details, or local user paths are committed.

## Metadata

- [ ] `name` is final.
- [ ] `version` is updated.
- [ ] `qgisMinimumVersion` is correct.
- [ ] `qgisMaximumVersion` is correct.
- [ ] `description` is short and accurate.
- [ ] `about` mentions Kakao API requirements and restrictions.
- [ ] `license=GPL-2.0-or-later` is present.
- [ ] `experimental=True` or `experimental=False` is intentional.

## Screenshots and Docs

- [ ] Add screenshots under `docs/screenshots/`.
- [ ] Review screenshots for API keys, account information, and sensitive locations.
- [ ] Add representative screenshots to `README.md`.
- [ ] Move detailed walkthrough screenshots to `docs/usage.md` if README becomes too long.

## Functional Smoke Test

- [ ] Install from ZIP in a clean QGIS profile.
- [ ] Enable the plugin from QGIS Plugin Manager.
- [ ] Open `Kakao Map / Roadview`.
- [ ] Set Kakao JavaScript API key.
- [ ] Confirm QGIS canvas center syncs to Kakao Map and Roadview.
- [ ] Confirm Kakao Map drag syncs back to QGIS.
- [ ] Confirm Roadview movement updates the QGIS roadview position layer.
- [ ] Confirm Local place/address search works.
- [ ] Set Kakao REST API key.
- [ ] Create a route with origin and destination.
- [ ] Create a route with at least one waypoint.
- [ ] Confirm route, route points, and guidance layers are created.
- [ ] Confirm guidance list item selection focuses the matching QGIS feature.
- [ ] Save route history to GeoPackage.
- [ ] Load route history from GeoPackage.
- [ ] Export route history to GeoJSON.
- [ ] Export route history to Shapefile.
- [ ] Export route history to GPX.
- [ ] Load GPX with sidecar QML styles.
- [ ] Test external browser integration mode when available.

## Package

- [ ] ZIP contains a single top-level `kakao_qgis_bridge/` folder.
- [ ] ZIP excludes `.git`, `.agents`, `.codex`, `__pycache__`, `.pytest_cache`, and local settings.
- [ ] ZIP excludes `kakao_qgis_bridge/settings.json`.
- [ ] ZIP excludes generated test/output files.
- [ ] ZIP size is below the QGIS repository package limit.
- [ ] Source code in the ZIP matches the public GitHub repository.

## Upload

- [ ] Log in to https://plugins.qgis.org/ with an OSGeo ID.
- [ ] Upload the plugin ZIP using "Share a plugin".
- [ ] Check the repository page for validation warnings.
- [ ] Watch the account email or plugin page for approval/rejection feedback.
