"""Audit existing plugin history files without changing them or user projects."""
import hashlib
import json
import sys
import tempfile
from pathlib import Path


def run(root, directory):
    sys.path.insert(0, str(root))
    from qgis.core import (Qgis, QgsApplication, QgsLineSymbol, QgsMarkerSymbol,
                           QgsSingleSymbolRenderer, QgsProject)
    from kakao_qgis_bridge.history_repository import HistoryRepository
    from kakao_qgis_bridge.history_import_service import HistoryImportService
    from kakao_qgis_bridge.history_export_service import HistoryExportService
    from kakao_qgis_bridge.history_formats import paired_output_paths
    app = QgsApplication([], False)
    app.initQgis()

    def repository():
        return HistoryRepository(lambda: QgsLineSymbol.createSimple({}),
            lambda: QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple({})))

    def signatures(path):
        if path.suffix.lower() == ".gpkg":
            paths = [path]
        else:
            paths = list(paired_output_paths(path, path.suffix.lower()))
            if path.suffix.lower() == ".shp":
                paths = [p.with_suffix(ext) for p in paths for ext in (".shp", ".dbf", ".shx", ".prj", ".cpg")]
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.exists()}

    candidates = sorted(p for p in directory.rglob("kakao*.gpkg"))
    candidates += sorted(p for p in directory.rglob("kakao*_routes.*") if p.suffix.lower() in (".geojson", ".shp"))
    results = []
    exporter = HistoryExportService(QgsProject.instance().transformContext())
    for index, path in enumerate(candidates):
        before = signatures(path)
        result = dict(file=str(path))
        try:
            repo = repository()
            service = HistoryImportService(repo)
            first = service.import_file(path)
            assert tuple(service.import_file(path)) == (0, 0)
            # Save each imported dataset in all three history formats, then
            # import into both an empty session and its original session.
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
                destination = Path(temporary)
                for suffix in (".gpkg", ".geojson", ".shp"):
                    output = destination / ("roundtrip" + suffix)
                    if suffix == ".gpkg":
                        exporter.write_geopackage_layer(repo.route_layer, output, "kakao_route_history", "LineString")
                        exporter.write_geopackage_layer(repo.guidance_layer, output, "kakao_guidance_history", "Point")
                    else:
                        rp, gp = paired_output_paths(output, suffix)
                        for layer, target, geometry, specs in (
                                (repo.route_layer, rp, "LineString", exporter._route_shapefile_fields()),
                                (repo.guidance_layer, gp, "Point", exporter._guidance_shapefile_fields())):
                            if suffix == ".geojson":
                                exporter.write_geojson_layer(layer, target, "history")
                            else:
                                exporter.write_shapefile_layer(layer, target, geometry, "history", specs)
                    imported = HistoryImportService(repository()).import_file(output)
                    assert tuple(imported) == tuple(first), (suffix, tuple(imported), tuple(first))
                    assert not any("5자리" in warning for warning in imported.warnings), suffix + " lost coordinate precision"
                    assert tuple(service.import_file(output)) == (0, 0), suffix
            result.update(status="ok", routes=first.routes, guides=first.guides, warnings=first.warnings,
                          repeated_import=True, all_format_roundtrips=True)
        except Exception as exc:
            result.update(status="error", error=str(exc))
        assert before == signatures(path), "Original file changed"
        result["source_unchanged"] = True
        results.append(result)
        print("SAVED_FILE=" + json.dumps(result, ensure_ascii=False), flush=True)
    return dict(qgis=Qgis.QGIS_VERSION, tested=len(results), errors=sum(r["status"] != "ok" for r in results))


if __name__ == "__main__":
    result = run(Path(sys.argv[1]), Path(sys.argv[2]))
    print("SAVED_AUDIT=" + json.dumps(result, ensure_ascii=False), flush=True)
    sys.exit(1 if result["errors"] else 0)
