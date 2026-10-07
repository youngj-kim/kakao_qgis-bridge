import copy
import json
import unittest

from kakao_qgis_bridge.mobility import (
    MobilityResponseError,
    RouteValidationError,
    guidance_category,
    normalize_route_request,
    parse_route_payload,
    route_query_items,
    route_http_error_message,
    validate_rest_api_key,
)


class MobilityTests(unittest.TestCase):
    @staticmethod
    def valid_payload():
        return {
            "trans_id": "test-route",
            "routes": [{
                "result_code": 0,
                "summary": {"distance": 1200, "duration": 180},
                "sections": [{
                    "roads": [{"vertexes": [126.9, 37.5, 127.0, 37.6]}],
                    "guides": [{"x": 126.9, "y": 37.5, "type": 2,
                                "guidance": "왼쪽 차로에서 우회전"}],
                }],
            }],
        }

    def test_rest_key_normalizes_outer_whitespace(self):
        self.assertEqual(validate_rest_api_key("  ascii-key123  "), "ascii-key123")

    def test_rest_key_rejects_invalid_header_values_without_echoing_key(self):
        for key in (None, 42, "", " ", "전각키", "ＡＢＣ", "secret key",
                    "secret\nkey", "secret\rkey", "secret\tkey", "secret\x00key",
                    "secret\x7fkey"):
            with self.subTest(key=key):
                with self.assertRaises(RouteValidationError) as error:
                    validate_rest_api_key(key)
                self.assertNotIn("secret", str(error.exception))

    def test_request_rejects_malformed_json_and_option_elements(self):
        for field, values in {
            "waypoints": (42, {}, "[", "{}", "[null]"),
            "avoid": (42, {}, "[", "{}", "[{}]", "[[]]", "[null]"),
            "vehicle": (42, {}, "[", "[]"),
        }.items():
            for value in values:
                args = {"waypoints": "[]", "avoid": "[]", "vehicle": "{}"}
                args[field] = value
                with self.subTest(field=field, value=value):
                    with self.assertRaises(RouteValidationError):
                        normalize_route_request(
                            126.9, 37.5, 127.1, 37.6, "RECOMMEND",
                            args["waypoints"], args["avoid"], args["vehicle"], "", "",
                        )

    def test_response_rejects_malformed_structure(self):
        cases = [None, [], "bad", {"routes": {}}, {"routes": [None]}]
        for path in (("sections",), ("summary",), ("sections", 0),
                     ("sections", 0, "roads"), ("sections", 0, "roads", 0),
                     ("sections", 0, "roads", 0, "vertexes")):
            for value in (42, "bad", {}):
                payload = self.valid_payload()
                target = payload["routes"][0]
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                # An empty summary object remains compatible with old responses.
                if path == ("summary",) and value == {}:
                    continue
                cases.append(payload)
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(MobilityResponseError):
                    parse_route_payload(payload)

    def test_response_rejects_invalid_distance_and_duration(self):
        for field in ("distance", "duration"):
            for value in ("bad", [], {}, True, -1, 1.5, float("inf"), float("nan")):
                payload = self.valid_payload()
                payload["routes"][0]["summary"][field] = value
                with self.subTest(field=field, value=value):
                    with self.assertRaises(MobilityResponseError):
                        parse_route_payload(payload)

    def test_response_rejects_broken_geometry_instead_of_joining_across_gap(self):
        for vertexes in ([126.9, 37.5, 127.0],
                         [126.9, 37.5, "bad", 37.55, 127.0, 37.6],
                         [126.9, 37.5, float("nan"), 37.6],
                         [126.9, 37.5, 181, 37.6]):
            payload = self.valid_payload()
            payload["routes"][0]["sections"][0]["roads"][0]["vertexes"] = vertexes
            with self.subTest(vertexes=vertexes):
                with self.assertRaises(MobilityResponseError):
                    parse_route_payload(payload)

    def test_optional_bad_guides_do_not_discard_valid_route(self):
        payload = self.valid_payload()
        section = payload["routes"][0]["sections"][0]
        valid_guide = copy.deepcopy(section["guides"][0])
        section["guides"] = [42, None, {}, {"x": 181, "y": 37.5},
                             dict(valid_guide, duration="bad"), valid_guide]
        result = parse_route_payload(payload)
        self.assertEqual(len(result.points), 2)
        self.assertEqual(len(result.guides), 1)
        self.assertEqual(result.guides[0]["sequence"], 1)
        self.assertEqual(result.guides[0]["category"], "right")
        section["guides"] = "bad"
        self.assertEqual(parse_route_payload(payload).guides, ())

    def test_known_guide_types_override_conflicting_text(self):
        groups = {
            "start": (100,), "destination": (101,), "waypoint": (1000,),
            "uturn": (3,), "straight": (0, 29), "other": (23,),
            "left": (1, 5, 8, 11, 24, 25, 26, 27, 28, 43, 46, 48, 82),
            "right": (2, 6, 9, 12, 18, 19, 20, 21, 22, 44, 47, 49, 83),
            "transition": (7, 10, 14, 15, 16, 17, 42, 45, 61, 62, 84, 85, 86, 300, 301),
            "roundabout": tuple(range(30, 42)) + tuple(range(70, 82)),
        }
        for category, codes in groups.items():
            for code in codes:
                with self.subTest(code=code):
                    self.assertEqual(guidance_category(code, ""), category)
                    self.assertEqual(guidance_category(code, "유턴 왼쪽 오른쪽 직진"), category)

    def test_unknown_guide_text_fallback_handles_ambiguity(self):
        for text, expected in (("좌회전", "left"), ("우회전", "right"),
                               ("직진", "straight"), ("유턴", "uturn"),
                               ("왼쪽 차로에서 오른쪽", "other"), ("", "other")):
            with self.subTest(text=text):
                self.assertEqual(guidance_category(999, text), expected)

    def test_http_errors_accept_non_object_payloads(self):
        for status, expected in ((401, "인증"), (403, "거부"), (429, "한도")):
            for payload in (None, [], "bad", {"msg": "provider-message"}):
                with self.subTest(status=status, payload=payload):
                    message = route_http_error_message(status, payload, "network error")
                    self.assertIn(expected, message)
                    self.assertIn(str(status), message)
        self.assertIn("network error", route_http_error_message(500, [], "network error"))
        self.assertIn("provider-message", route_http_error_message(400, {"msg": "provider-message"}, ""))

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
