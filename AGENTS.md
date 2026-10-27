# Release preparation

- Before building any final distribution ZIP, update both CHANGELOG.md and kakao_qgis_bridge/metadata.txt for the target version.
- metadata.txt must include a concise English changelog for that version with the same user-visible changes and accurate verification scope as CHANGELOG.md. QGIS uses it to prefill the upload changelog; it does not upload the package automatically.
- Verify the exported ZIP contains the updated version and changelog, and regenerate checksums and validation reports for any new package.
- Do not overwrite a package already uploaded or confirmed as immutable. Repository upload, push and release creation require authorization from the user.
