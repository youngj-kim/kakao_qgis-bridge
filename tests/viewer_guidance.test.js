const assert = require("node:assert/strict");
const { test } = require("node:test");
const { Element, loadController, createDocument } = require("./viewer_test_support");

function harness(mapReady = true) {
  const nodes = Object.fromEntries(["routeGuidanceList", "routeGuidanceSummaryText", "routeGuidanceOverview",
    "routeGuidancePanel", "routeGuidanceToggle"].map((name) => [name, new Element()]));
  const lines = [], bounds = [], moves = [], selections = [], messages = [];
  let tab = "guidance";
  const sdk = {
    LatLng: function (lat, lon) { this.lat = lat; this.lon = lon; },
    Polyline: function (options) {
      this.options = options;
      this.setMap = (map) => { this.removed = map === null; };
      lines.push(this);
    },
    LatLngBounds: function () { this.points = []; this.extend = (point) => this.points.push(point); }
  };
  const controller = loadController("guidance").createKakaoGuidanceController({
    ...nodes, document: createDocument(), getMap: () => mapReady ? { setBounds: (value) => bounds.push(value) } : null,
    getMaps: () => sdk, getBridge: () => ({ selectRouteGuidance: (...args) => selections.push(args) }),
    getActiveTab: () => tab, moveViewer: (...args) => moves.push(args), setStatus: (message) => messages.push(message),
    formatCoordinate: ({ lon, lat }) => lon.toFixed(7) + ", " + lat.toFixed(7),
    activateRoutePanelTab: (value) => { tab = value; },
    updateRoutePanelVisibility() {}, scheduleStableRelayout() {}
  });
  return { ...nodes, controller, lines, bounds, moves, selections, messages,
    setMapReady(value) { mapReady = value; } };
}
const payload = {
  origin: { label: "<출발>", lon: 127, lat: 37.5 }, destination: { label: "도착", lon: 128, lat: 38 },
  summary: { distance_m: 1500, duration_s: 120, avoid: ["toll"], vehicle: { car_type: 1 } },
  path: [{ lon: 127, lat: 37.5 }, { lon: "bad", lat: 38 }, { lon: 128, lat: 38 }],
  guides: [{ sequence: 1, guidance: "<좌회전 & 진입>", category: "left",
    longitude: 127, latitude: 37.5, distance_m: 200, duration_s: 30 }]
};

test("guidance renders safe text, summary, overview and finite route vertices", () => {
  const h = harness();
  h.controller.render(payload);
  assert.equal(h.controller.count, 1);
  assert.equal(h.lines[0].options.path.length, 2);
  assert.equal(h.bounds[0].points.length, 2);
  assert.match(h.routeGuidanceSummaryText.dataset.guidanceSummary, /2분 · 1.5 km/);
  assert.match(h.routeGuidanceOverview.textContent, /<출발>/);
  assert.match(h.routeGuidanceList.textContent, /<좌회전 & 진입>/);
  h.routeGuidanceList.children[0].fire("click");
  assert.deepEqual(h.moves, [[127, 37.5]]);
  assert.deepEqual(h.selections, [[1, 127, 37.5]]);
  assert.equal(h.controller.activeSequence, 1);
});
test("replacing/clearing guidance removes old SDK overlay and active selection", () => {
  const h = harness();
  h.controller.render(payload);
  h.routeGuidanceList.children[0].fire("click");
  h.controller.render(payload);
  assert.equal(h.lines[0].removed, true);
  assert.equal(h.controller.activeSequence, null);
  h.controller.render({});
  assert.equal(h.lines[1].removed, true);
  assert.equal(h.controller.count, 0);
  assert.equal(h.routeGuidanceList.children.length, 0);
  assert.equal(h.routeGuidanceOverview.hidden, true);
});
test("guidance before SDK startup is cached and renders when the map is ready", () => {
  const h = harness(false);
  h.controller.render(payload);
  assert.equal(h.lines.length, 0);
  assert.equal(h.controller.payload, payload);
  assert.equal(h.controller.count, 1);
  h.setMapReady(true);
  h.controller.render(h.controller.payload);
  assert.equal(h.lines.length, 1);
});
test("formatting and input labels retain coordinate fallback behavior", () => {
  const h = harness();
  assert.equal(h.controller.formatDistance(999), "999 m");
  assert.equal(h.controller.formatDuration(30), "30초");
  assert.equal(h.controller.formatDistance(NaN), "");
  assert.equal(h.controller.inputLabel({ lon: 127, lat: 37.5 }, "fallback"), "127.0000000, 37.5000000");
  assert.equal(h.controller.inputLabel({}, "fallback"), "fallback");
});
