const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const html = fs.readFileSync(path.join(__dirname, "..", "kakao_qgis_bridge", "web", "kakao_viewer.html"), "utf8");
// Execute the production functions with a fake SDK, without an API key/network.
const functions = ["syncKakaoMapToQgis", "moveViewer", "updateRoadviewPosition"]
  .map((name) => html.match(new RegExp(`    function ${name}\\([^]*?\\n    \\}`))[0])
  .join("\n");
const dragEnd = html.match(/addListener\(map, "dragend", (\(\) => \{[^]*?\n      \})\);/)[1];

function harness(connected = true) {
  const lookups = [];
  const panos = [];
  const moves = [];
  const mapCenters = [];
  const messages = [];
  let current;
  const point = (lon, lat) => ({ getLng: () => lon, getLat: () => lat });
  current = point(127, 37.5);
  const context = vm.createContext({
    map: { getCenter: () => current, setCenter: (position) => mapCenters.push(position) },
    marker: { setPosition() {} },
    roadviewClient: { getNearestPanoId(position, radius, callback) { lookups.push({ position, radius, callback }); } },
    roadview: { setPanoId(panoId, position) { panos.push({ panoId, position }); } },
    qgisBridge: connected ? { moveQgisCenter: (lon, lat) => moves.push([lon, lat]) } : null,
    kakao: { maps: { LatLng: function (lat, lon) { return point(lon, lat); } } },
    setStatus: (message) => messages.push(message),
    window: { clearTimeout() {} },
  });
  vm.runInContext(`let moveRequestId = 0; let programmaticRoadviewPanoId = null; let mapSyncTimer = null;\n${functions}\nconst onDragEnd = ${dragEnd};`, context);
  return { context, lookups, panos, moves, mapCenters, messages,
    dragEnd() { vm.runInContext("onDragEnd()", context); },
    move(lon, lat) { current = point(lon, lat); },
  };
}

test("map drag end updates local Roadview without waiting for a QGIS echo", () => {
  const h = harness();
  h.dragEnd();
  assert.deepEqual(h.moves, [[127, 37.5]]);
  assert.equal(h.lookups.length, 1);
  assert.equal(h.lookups[0].radius, 80);
  assert.equal(h.mapCenters.length, 0, "Drag must not recenter the map");
  h.lookups[0].callback(123);
  assert.equal(h.panos[0].panoId, 123);
  assert.equal(vm.runInContext("programmaticRoadviewPanoId", h.context), 123);
});

test("local Roadview updates even when the QGIS bridge is not ready", () => {
  const h = harness(false);
  h.dragEnd();
  h.lookups[0].callback(123);
  assert.equal(h.panos.length, 1);
});

test("continuous drag forwards center without a panorama lookup for every tick", () => {
  const h = harness();
  vm.runInContext("syncKakaoMapToQgis()", h.context);
  assert.equal(h.moves.length, 1);
  assert.equal(h.lookups.length, 0);
  h.dragEnd();
  assert.equal(h.lookups.length, 1);
});

test("old panorama callbacks cannot replace the latest drag destination", () => {
  const h = harness();
  h.dragEnd();
  h.move(128, 38);
  h.dragEnd();
  h.lookups[1].callback(222);
  h.lookups[0].callback(111);
  assert.deepEqual(h.panos.map((pano) => pano.panoId), [222]);
  assert.equal(h.panos[0].position.getLng(), 128);
});

test("missing nearby panorama shows a message without loading an invalid ID", () => {
  const h = harness();
  h.dragEnd();
  h.lookups[0].callback(null);
  assert.equal(h.panos.length, 0);
  assert.match(h.messages.at(-1), /촬영 지점이 없습니다/);
});

test("QGIS-driven moves still update both map and Roadview", () => {
  const h = harness();
  vm.runInContext("moveViewer(128, 38)", h.context);
  h.lookups[0].callback(333);
  assert.equal(h.mapCenters[0].getLng(), 128);
  assert.equal(h.panos[0].panoId, 333);
  assert.equal(h.moves.length, 0);
});
