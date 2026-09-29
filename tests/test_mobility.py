import json
import unittest

from kakao_qgis_bridge.mobility import (
    MobilityResponseError,
    RouteValidationError,
    normalize_route_request,
    parse_route_payload,
    route_query_items,
)


class MobilityTests(unittest.TestCase):
    def test_normalizes_request_and_filters_options(self):
        request = normalize_route_request(
            126.9,
            37.5,
            127.1,
            37.6,
            "UNKNOWN",
            json.dumps([{"lon": 127.0, "lat": 37.55, "label": "경유"}]),
            json.dumps(["toll", "invalid", "toll"]),
            json.dumps({"car_type": 99, "car_fuel": "ELECTRIC", "car_hipass": True}),
            " 출발 ",
            " 도착 ",
        )
        self.assertEqual(request.priority, "RECOMMEND")
        self.assertEqual(request.avoid_options, ("toll",))
        self.assertEqual(request.vehicle_options["car_type"], 1)
        self.assertEqual(request.vehicle_options["car_fuel"], "GASOLINE")
        self.assertEqual(request.origin_label, "출발")
        query = dict(route_query_items(request))
        self.assertEqual(query["car_hipass"], "true")
        self.assertIn("127.00000000,37.55000000", query["waypoints"])

    def test_rejects_out_of_range_coordinate(self):
        with self.assertRaises(RouteValidationError):
            normalize_route_request(
                181,
                37.5,
                127.1,
                37.6,
                "RECOMMEND",
                "[]",
                "[]",
                "{}",
                "",
                "",
            )

    def test_parses_route_and_guidance(self):
        result = parse_route_payload(
            {
                "trans_id": "route-1",
                "routes": [
                    {
                        "result_code": 0,
                        "summary": {"distance": 1200, "duration": 180},
                        "sections": [
                            {
                                "roads": [{"vertexes": [126.9, 37.5, 127.0, 37.6]}],
                                "guides": [
                                    {
                                        "x": 126.9,
                                        "y": 37.5,
                                        "type": 100,
                                        "guidance": "출발",
                                        "distance": 0,
                                        "duration": 0,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        )
        self.assertEqual(result.route_id, "route-1")
        self.assertEqual(result.distance, 1200)
        self.assertEqual(result.guides[0]["category"], "start")

    def test_rejects_empty_result(self):
        with self.assertRaises(MobilityResponseError):
            parse_route_payload({"routes": []})


if __name__ == "__main__":
    unittest.main()
