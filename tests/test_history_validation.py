import unittest
from kakao_qgis_bridge.history_validation import (ImportReport, integer, coordinate, normalize_values)


class HistoryValueTests(unittest.TestCase):
    def test_integer_rejects_lossy_and_out_of_range_values(self):
        for value in (True, 1.5, 1.0, "1.5", "NaN", -1, 2147483648):
            with self.subTest(value=value), self.assertRaises(ValueError):
                integer(value)
        self.assertEqual(integer(" 12 "), 12)

    def test_coordinates_reject_nonfinite_bool_and_ranges(self):
        for value in (True, float("nan"), float("inf"), "inf", 181):
            with self.subTest(value=value), self.assertRaises(ValueError):
                coordinate(value)
        with self.assertRaises(ValueError):
            coordinate(91, True)

    def route(self, **changes):
        values = dict(history_id="h1", origin_lon=127, origin_lat=37,
                      destination_lon=127.1, destination_lat=37.1)
        values.update(changes)
        return values

    def test_legacy_defaults_preserve_provided_metadata(self):
        report = ImportReport()
        values, provided = normalize_values(self.route(), "route", False, report)
        self.assertEqual(values["schema_ver"], 2)
        self.assertEqual(values["car_type"], 1)
        self.assertNotIn("distance_m", provided)
        self.assertTrue(report.warnings)

    def test_future_schema_and_invalid_required_fields(self):
        for changes in (dict(schema_ver=3), dict(schema_ver=0), dict(history_id=" "),
                        dict(history_id="x" * 37), dict(origin_lon=None), dict(car_type=99)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                normalize_values(self.route(**changes), "route", False, ImportReport())

    def test_shp_parse_loss_is_distinct_from_bad_coordinates(self):
        report = ImportReport()
        values, _ = normalize_values(self.route(waypoints_json='[{"lon":'), "route", True, report)
        self.assertEqual(values["waypoints_json"], "[]")
        self.assertTrue(any("SHP" in warning for warning in report.warnings))
        for shp, text in ((False, '{'), (True, '[{"lon":999,"lat":37}]'), (True, '{}')):
            with self.subTest(shp=shp, text=text), self.assertRaises(ValueError):
                normalize_values(self.route(waypoints_json=text), "route", shp, ImportReport())

    def test_guide_road_index_sentinel_is_preserved(self):
        guide = dict(history_id="h1", sequence=1, longitude=127, latitude=37, road_index=-1)
        values, _ = normalize_values(guide, "guidance", False, ImportReport())
        self.assertEqual(values["road_index"], -1)
        guide["road_index"] = -2
        with self.assertRaises(ValueError):
            normalize_values(guide, "guidance", False, ImportReport())


if __name__ == "__main__":
    unittest.main()
