import unittest

from kakao_qgis_bridge.fare_values import fare_amount
from kakao_qgis_bridge.mobility import parse_route_payload, MobilityResponseError
from kakao_qgis_bridge.history_validation import normalize_values, ImportReport


class FareTests(unittest.TestCase):
    def payload(self, fare=None):
        summary = dict(distance=100, duration=20)
        if fare is not None:
            summary["fare"] = fare
        return {"routes": [dict(result_code=0, summary=summary,
                               sections=[dict(roads=[dict(vertexes=[127, 37, 127.1, 37.1])])])]}

    def test_unknown_and_zero_are_distinct(self):
        self.assertIsNone(fare_amount(None))
        self.assertEqual(fare_amount(0), 0)
        self.assertEqual(fare_amount(21000), 21000)

    def test_bad_fares_rejected(self):
        for value in (True, -1, 0.5, "100", float("nan"), float("inf"), 2147483648, 10 ** 1000):
            with self.subTest(value=value), self.assertRaises(ValueError):
                fare_amount(value)

    def test_api_fares_and_absence(self):
        result = parse_route_payload(self.payload(dict(toll=0, taxi=12300)))
        self.assertEqual((result.toll_fare, result.taxi_fare), (0, 12300))
        result = parse_route_payload(self.payload())
        self.assertEqual((result.toll_fare, result.taxi_fare), (None, None))
        result = parse_route_payload(self.payload(dict(toll=1200)))
        self.assertEqual((result.toll_fare, result.taxi_fare), (1200, None))

    def test_malformed_api_fare_rejected(self):
        for fare in ([], dict(toll=-1), dict(taxi=True)):
            with self.subTest(fare=fare), self.assertRaises(MobilityResponseError):
                parse_route_payload(self.payload(fare))

    def test_legacy_history_does_not_invent_zero(self):
        route = dict(history_id="h", origin_lon=127, origin_lat=37,
                     destination_lon=127.1, destination_lat=37.1)
        values, provided = normalize_values(route, "route", False, ImportReport())
        self.assertIsNone(values["toll_fare"])
        self.assertIsNone(values["taxi_fare"])
        self.assertNotIn("toll_fare", provided)
        route.update(toll_fare=0, taxi_fare=15000)
        values, provided = normalize_values(route, "route", False, ImportReport())
        self.assertEqual((values["toll_fare"], values["taxi_fare"]), (0, 15000))
        self.assertIn("toll_fare", provided)
