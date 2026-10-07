"""Multi-history batch semantics and isolated validation timings in real QGIS."""
import copy
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qgis.core import Qgis, QgsApplication, QgsGeometry, QgsPointXY
from kakao_qgis_bridge.history_import_service import HistoryImportService as Service
from kakao_qgis_bridge.history_validation import ImportReport, HistoryValidationError, normalize_values

app = QgsApplication([], False)
app.initQgis()
line = QgsGeometry.fromPolylineXY([QgsPointXY(127, 37), QgsPointXY(127.1, 37.1)])
point = QgsGeometry.fromPointXY(QgsPointXY(127.01, 37.01))

def rows(hid, count=2):
    route, provided = normalize_values(dict(
        schema_ver=2, history_id=hid, route_id="r" + hid, origin_lon=127, origin_lat=37,
        destination_lon=127.1, destination_lat=37.1, distance_m=100, duration_s=10,
        guidance_count=count), "route", False, ImportReport())
    guides = []
    for seq in range(1, count + 1):
        values, fields = normalize_values(dict(
            schema_ver=2, history_id=hid, route_id="r" + hid, sequence=seq,
            longitude=127.01, latitude=37.01, distance_m=20, duration_s=2, guide_type=0),
            "guidance", False, ImportReport())
        guides.append((values, fields, QgsGeometry(point), f"{hid}:{seq}"))
    return (route, provided, QgsGeometry(line), hid), guides

def validate(routes, guides, old_routes=(), old_guides=()):
    report = ImportReport()
    accepted = Service.validate_batch(routes, guides, old_routes, old_guides, report)
    return accepted, report

def clone(row):
    return (copy.deepcopy(row[0]), set(row[1]), QgsGeometry(row[2]), row[3])

def reject(routes, guides, old_routes=(), old_guides=()):
    try:
        validate(routes, guides, old_routes, old_guides)
    except HistoryValidationError:
        return
    raise AssertionError("conflicting batch accepted")

r0, g0 = rows("existing")
r1, g1 = rows("new-1", 3)
r2, g2 = rows("new-2", 0)
accepted, report = validate([r0, r1, r2, r1], g1 + g0 + [g1[0]], [r0], g0)
assert [row[0]["history_id"] for row in accepted[0]] == ["new-1", "new-2"]
assert {(row[0]["history_id"], row[0]["sequence"]) for row in accepted[1]} == {
    ("new-1", 1), ("new-1", 2), ("new-1", 3)}
assert (report.skipped_routes, report.skipped_guides, report.duplicates) == (1, 2, 2)

# Restore missing count after duplicate elimination, without counting twice.
missing = clone(r1)
missing[0]["guidance_count"] = 0
missing[1].remove("guidance_count")
accepted, report = validate([missing], g1 + [g1[0]])
assert accepted[0][0][0]["guidance_count"] == 3 and report.duplicates == 1
assert report.warnings

# Replenish guides for a matching route, ignoring unrelated session guides.
accepted, _ = validate([], g1, [r0, r1], g0)
assert not accepted[0] and len(accepted[1]) == 3
reject([], g0[:1], [r0], g0)  # Partial existing guide set.
reject([], g1[:1], [r1], [])  # Replenishment must match stored count.
reject([], g1)                # Orphan guides.
bad = clone(g0[0])
bad[0]["route_id"] = "different"
reject([r0], [bad, g0[1]], [r0], g0)
bad = clone(g0[0])
bad[0]["guide_type"] = 99
bad[1].add("guide_type")
reject([r0], [bad, g0[1]], [r0], g0)
bad = clone(g1[0])
bad[0]["distance_m"] += 1
reject([r1], g1 + [bad])       # Same identity with conflicting values.

# Timings exclude file IO, normalization, provider writes and recovery snapshots.
timings = []
for size in (500, 2000):
    routes, guides = [], []
    for index in range(size):
        route, group = rows(f"bench-{index}", 3)
        routes.append(route)
        guides.extend(group)
    start = time.perf_counter()
    accepted, report = validate(routes, guides, routes, guides)
    elapsed = time.perf_counter() - start
    assert not any(accepted)
    assert (report.skipped_routes, report.skipped_guides) == (size, size * 3)
    timings.append(dict(routes=size, guides=len(guides), seconds=round(elapsed, 6)))
print("IMPORT_BATCH_RESULT=" + json.dumps(dict(qgis=Qgis.QGIS_VERSION, status="ok",
    checks=["multiple IDs", "zero guides", "duplicates", "derived count", "guide replenishment",
            "partial sets", "orphans", "route ID conflict", "guide conflict"], timings=timings)), flush=True)
