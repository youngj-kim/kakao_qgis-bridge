"""Compare applied fingerprints with original semantics and append costs."""
import json
import sys
import time
from statistics import median
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qgis.core import (NULL, Qgis, QgsApplication, QgsFeature, QgsGeometry,
                       QgsLineSymbol, QgsMarkerSymbol, QgsPointXY, QgsSingleSymbolRenderer,
                       )
from qgis.PyQt.QtCore import QDate, QDateTime
from kakao_qgis_bridge.history_repository import HistoryRepository
from kakao_qgis_bridge.history_operations import HistoryOperations, HistoryOperationError
from kakao_qgis_bridge.history_validation import ImportReport, normalize_values
from history_key_reference import reference_key

app = QgsApplication([], False)
app.initQgis()

# Compare the applied implementation with the independent original algorithm.
variant_checks = []
for value in (None, NULL, "", "NULL", "한글", True, False, 0, 1, 0.0, -0.0,
              float("nan"), float("inf"), QDate(), QDate(2026, 10, 7), QDateTime()):
    feature = QgsFeature()
    feature.setAttributes([value])
    same = HistoryOperations._key(feature) == reference_key(feature)
    assert same, f"applied key differs for {type(value).__name__}"
    variant_checks.append(type(value).__name__)

near_a = QgsGeometry.fromPointXY(QgsPointXY(127, 37))
near_b = QgsGeometry.fromPointXY(QgsPointXY(127 + 1e-9, 37))
geometry_check = dict(native_equals=near_a.equals(near_b),
                      wkb_equal=bytes(near_a.asWkb()) == bytes(near_b.asWkb()))
results = []
for size in (200, 1000):
    repo = HistoryRepository(lambda: QgsLineSymbol.createSimple({}),
                             lambda: QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple({})))
    routes, guides = repo.ensure_layers()
    geometry = QgsGeometry.fromPolylineXY([QgsPointXY(127 + index * 1e-6, 37) for index in range(500)])
    rv, _ = normalize_values(dict(history_id="seed", route_id="seed", schema_ver=2,
        origin_lon=127, origin_lat=37, destination_lon=127.000499, destination_lat=37,
        guidance_count=4), "route", False, ImportReport())
    gv, _ = normalize_values(dict(history_id="seed", route_id="seed", schema_ver=2,
        sequence=1, longitude=127, latitude=37), "guidance", False, ImportReport())
    def make(layer, values, geom, hid, seq=None):
        feature = QgsFeature(layer.fields())
        data = dict(values, history_id=hid, route_id=hid)
        if seq is not None:
            data["sequence"] = seq
        feature.setAttributes([data.get(name) for name in layer.fields().names()])
        feature.setGeometry(geom)
        return feature
    rrows = [make(routes, rv, geometry, f"h{index}") for index in range(size)]
    grows = [make(guides, gv, near_a, f"h{index}", seq)
             for index in range(size) for seq in range(1, 5)]
    assert routes.dataProvider().addFeatures(rrows)[0]
    assert guides.dataProvider().addFeatures(grows)[0]
    for layer in (routes, guides):
        for feature in layer.getFeatures():
            assert HistoryOperations._key(feature) == reference_key(feature)
    ops = repo._operations
    measurements = []
    for mode in [mode for _ in range(3) for mode in ("baseline", "optimized")]:
        stats = dict(features_seconds=0.0, key_seconds=0.0, key_calls=0)
        original_features = ops._features
        key = ops._key if mode == "optimized" else reference_key
        def features(layer):
            start = time.perf_counter()
            result = original_features(layer)
            stats["features_seconds"] += time.perf_counter() - start
            return result
        def fingerprint(feature):
            start = time.perf_counter()
            result = key(feature)
            stats["key_seconds"] += time.perf_counter() - start
            stats["key_calls"] += 1
            return result
        hid = "new-" + mode
        changes = [(routes, [make(routes, rv, geometry, hid)], []),
                   (guides, [make(guides, gv, near_a, hid, seq) for seq in range(1, 5)], [])]
        with patch.object(ops, "_features", side_effect=features), \
                patch.object(ops, "_key", side_effect=fingerprint):
            start = time.perf_counter()
            assert ops.apply("profile", changes) == (5, 0)
            stats["total_seconds"] = time.perf_counter() - start
        stats["mode"] = mode
        measurements.append(stats)
        # Both modes start with the same number of stored features.
        repo.delete_history(hid)
    # Verify why ID/count-only success cannot maintain the old-content guarantee.
    before = ops._contents(ops._features(routes))
    original_add = ops._provider_add
    old = next(routes.getFeatures())
    routes.selectByIds([old.id()])
    injected = [False]
    def corrupting_add(layer, incoming):
        result = original_add(layer, incoming)
        if layer is routes and not injected[0]:
            injected[0] = True
            assert layer.dataProvider().changeAttributeValues({old.id(): {
                layer.fields().indexOf("origin_name"): "corrupted"}})
        return result
    with patch.object(ops, "_provider_add", side_effect=corrupting_add):
        try:
            ops.apply("corruption probe", [(routes, [make(routes, rv, geometry, "bad")], [])])
        except HistoryOperationError as exc:
            assert exc.recovered
        else:
            raise AssertionError("existing-data corruption accepted")
    assert ops._contents(ops._features(routes)) == before
    assert routes.selectedFeatureCount() == 1
    summaries = []
    for mode in ("baseline", "optimized"):
        runs = [measurement for measurement in measurements if measurement["mode"] == mode]
        summaries.append(dict(mode=mode, repeats=len(runs), **{
            name: median(measurement[name] for measurement in runs)
            for name in ("features_seconds", "key_seconds", "key_calls", "total_seconds")}))
    results.append(dict(routes=size, guides=size * 4, route_vertices=500,
                        measurements=summaries, existing_corruption="detected and recovered"))
print("OPERATIONS_PROFILE=" + json.dumps(dict(qgis=Qgis.QGIS_VERSION,
    variant_checks=variant_checks, geometry_check=geometry_check, results=results)), flush=True)
