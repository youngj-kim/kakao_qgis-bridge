# GitHub and ZIP Distribution Checklist

> 과거 개발·검토 기록입니다. 당시 버전과 검증 결과를 보존하며, 현재 배포 상태는 [배포 체크리스트](../release-checklist.md)를 참고하세요.

Distribution scope (2026-10-08): GitHub source and ZIP files. The user has
excluded uploading to the official QGIS plugin repository. Historical upload
items below are retained as past planning, not current tasks.

## Current 1.2.1 status — 2026-10-12

### Release-review candidate (supersedes the earlier test ZIP below)

- [x] Clean user-facing README; record development/test notes in refactoring-progress.md.
- [x] Add versioned GPKG comparison changelog; ordered 20m waypoint matching, explicit styles and temporary-layer policy.
- [x] Defer comparison geometry reading to selected routes and detect ordinary source-file changes.
- [x] Make project reset informational, preserve Ctrl/Meta wheel defaults, remove unused imports and normalize text to LF.
- [x] Keep the agreed missing-waypoint-result-pin omission policy unchanged.
- [x] Run Python 75 / JavaScript 49 tests, syntax/compile checks and Bandit with no findings.
- [ ] Manually install `dist/kakao_qgis_bridge-1.2.1-release-review-test.zip` in QGIS 3 and 4; confirm SDK interaction and browser Ctrl+wheel behavior.

This ZIP replaces neither an earlier immutable test ZIP nor its historical confirmation.
Source commit/push, CI and final official upload remain separate release steps.

### Post-review structural candidate (not yet manually confirmed)

- [x] Extract RouteController, ViewerAdapter and viewer_sync.js without changing file schemas or bridge contracts.
- [x] Run Python 75 / JavaScript 48 tests and Bandit with no findings.
- [x] Run QGIS 3.44.14/4.2.2 route-controller, pin, zoom, bridge, project, history/failure, export and display regressions.
- [ ] Manually install `dist/kakao_qgis_bridge-1.2.1-refactoring-complete-test.zip` in QGIS 3 and 4 and confirm actual SDK interaction.
- [ ] Commit/push this structural candidate and confirm its CI before final distribution.

The following confirmations refer to the earlier fb5c261 code/clean-pins ZIP.
They are not manual approval of this newer structural candidate. See refactoring-finalization.md.

This section supersedes earlier candidate checklists. Code is pushed to main at
fb5c261. No release/tag or official repository upload is implied by a source push.

- [x] Complete the planned history/export/layer/viewer controller refactoring.
- [x] Add bidirectional QGIS/Kakao Map zoom while retaining Roadview position on zoom-only changes.
- [x] Align route result/history pins with API guidance positions and hide duplicate current guidance pins.
- [x] Run Python 69 and JavaScript 45 tests before the code commit.
- [x] Run QGIS 3.44.14/4.2.2 zoom, bridge, route-pin and display-layer runtime checks.
- [x] Record user confirmations: import/export, search/map/Roadview, route editing/search, bidirectional zoom and duplicate-pin cleanup. These were incremental checks, not a fresh exhaustive final-package matrix.
- [x] Verify the tested clean-pins ZIP: 45 files, source agreement and settings/cache excluded.
- [x] Commit/push the fixes: fb5c261, main.
- [x] Update current README, usage, metadata changelog and validation documentation; retain historical records.
- [ ] Confirm CI for fb5c261; the earlier CI result below does not establish this commit's status.
- [ ] Validate declared minimum QGIS 3.34 in a runnable environment.
- [ ] Confirm SDK terms/quota suitability; no approval is inferred from successful operation.
- [ ] Confirm the final distribution ZIP after documentation updates; create release/tag only on request.

User-confirmed installation ZIP: `dist/kakao_qgis_bridge-1.2.1-clean-pins-test.zip`.
SHA-256: `39f7eb58db7d713a4807e24e1147b27393f50a6b33d42e21e35d3718412711f4`.
This immutable test ZIP predates the documentation refresh; it has not been rebuilt
or renamed as the final distribution package. Older ZIPs are retained.
See route-points-fix.md and zoom-roadview-policy.md for scope and limitations.

## Historical 1.2.1 candidate — 2026-10-08

This section tracks the latest cumulative refactoring candidate. Earlier checked
items below do not establish that this ZIP was manually installed and tested.

- [x] Extract history and export UI controllers.
- [x] Extract viewer search, guidance, history and route-input controllers.
- [x] Review optional SDK/layout separation; retain shared synchronization state.
- [x] Check project boundaries and late route-location callbacks.
- [x] Run Python 62 and JavaScript 37 tests, syntax checks and compilation.
- [x] Run QGIS 3.44.14/4.2.2 HTML assembly, bridge, project, history and export regressions.
- [x] Run Bandit 1.9.4: no findings, no skipped files or disabled test rules.
- [x] Update metadata, descriptions, changelog and installation notes to 1.2.1 candidate.
- [x] Verify candidate ZIP: 45 files, integrity/source agreement and local settings/cache excluded.
- [x] Commit/push cumulative source changes: 3e35f5a, main.
- [x] Confirm source CI: Windows/Ubuntu success, Actions run 37752581869.
- [ ] Manually install the latest candidate and test actual Kakao SDK in QGIS 3 and 4.
- [ ] Validate declared minimum QGIS 3.34 when a runnable environment is available.
- [ ] Confirm SDK terms and quota suitability for the intended use.
- [ ] Final release/tag only after the required manual checks and a release request.

Candidate: dist/kakao_qgis_bridge-1.2.1.zip.
See route-input-refactoring.md for scope, test boundaries and the manual checklist.

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
