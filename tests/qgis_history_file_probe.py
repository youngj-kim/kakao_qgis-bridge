"""Read a supplied history file into temporary memory; verify source unchanged."""
import hashlib
import json
import sys
import tempfile
from pathlib import Path


def run(root, path):
    sys.path.insert(0, str(root))
    from qgis.core import (Qgis, QgsApplication, QgsLineSymbol, QgsMarkerSymbol,
                           QgsSingleSymbolRenderer)
    from kakao_qgis_bridge.history_repository import HistoryRepository
    from kakao_qgis_bridge.history_import_service import HistoryImportService
    app = QgsApplication([], False)
    app.initQgis()
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    repository = HistoryRepository(lambda: QgsLineSymbol.createSimple({}),
        lambda: QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple({})))
    service = HistoryImportService(repository)
    first = service.import_file(path)
    again = service.import_file(path)
    assert tuple(again) == (0, 0), "Repeated import did not deduplicate"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original, "Source changed"
    # Re-export the actual legacy data and verify the paired GeoJSON path too.
    from qgis.core import QgsProject
    from kakao_qgis_bridge.history_export_service import HistoryExportService
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        exporter = HistoryExportService(QgsProject.instance().transformContext())
        for layer, name in ((repository.route_layer, "routes"), (repository.guidance_layer, "guidance")):
            exporter.write_geojson_layer(layer, Path(directory) / f"probe_{name}.geojson", "history")
        fresh = HistoryRepository(lambda: QgsLineSymbol.createSimple({}),
            lambda: QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple({})))
        imported = HistoryImportService(fresh).import_file(Path(directory) / "probe_routes.geojson")
        assert tuple(imported) == tuple(first)
        # Export straight from the source to retain its rounded attributes.
        routes, guides = service.open_sources(path)
        for layer, name in ((routes, "routes"), (guides, "guidance")):
            exporter.write_geojson_layer(layer, Path(directory) / f"legacy_{name}.geojson", "history")
        fresh = HistoryRepository(lambda: QgsLineSymbol.createSimple({}),
            lambda: QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple({})))
        legacy = HistoryImportService(fresh).import_file(Path(directory) / "legacy_routes.geojson")
        assert tuple(legacy) == tuple(first)
    return dict(status="ok", qgis=Qgis.QGIS_VERSION, routes=first.routes, guides=first.guides,
                warnings=first.warnings, source_unchanged=True, geojson_roundtrip=True,
                legacy_geojson_rounding=True)


if __name__ == "__main__":
    print("FILE_PROBE=" + json.dumps(run(Path(sys.argv[1]), Path(sys.argv[2])), ensure_ascii=False))
