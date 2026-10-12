const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const source = fs.readFileSync(path.join(__dirname, "..", "kakao_qgis_bridge", "web", "viewer_sync.js"), "utf8");
// Exercise the complete production controller, without an API key/network.

function harness(connected = true) {
  const lookups = [];
  const panos = [];
  const moves = [];
  const mapCenters = [];
  const messages = [];
  const markerPositions = [];
  let current;
  const point = (lon, lat) => ({ getLng: () => lon, getLat: () => lat });
  current = point(127, 37.5);
  const context = vm.createContext({
    map: { getCenter: () => current, setCenter: (position) => mapCenters.push(position) },
    marker: { setPosition(position) { markerPositions.push(position); } },
    roadviewClient: { getNearestPanoId(position, radius, callback) { lookups.push({ position, radius, callback }); } },
    roadview: { setPanoId(panoId, position) { panos.push({ panoId, position }); },
      getPanoId: () => panos.at(-1)?.panoId },
    qgisBridge: connected ? { moveQgisCenter: (lon, lat) => moves.push([lon, lat]) } : null,
    kakao: { maps: { LatLng: function (lat, lon) { return point(lon, lat); } } },
    setStatus: (message) => messages.push(message),
    window: { clearTimeout() {}, setTimeout() { return 1; } },
  });
  vm.runInContext(source + `
    const controller = window.createKakaoViewerSync({
      document: { getElementById: (...args) => document.getElementById(...args) },
      timers: window, getMap: () => map, getMarker: () => marker,
      getRoadview: () => roadview, getRoadviewClient: () => roadviewClient,
      getMaps: () => kakao.maps, getBridge: () => qgisBridge, setStatus
    });
    const { moveViewer, syncKakaoMapToQgis, configureMapWheel, mapMetersPerPixel,
      applyMapResolution, scheduleMapZoomSync, onMapDragEnd: onDragEnd } = controller;
  `, context);
  return { context, lookups, panos, moves, mapCenters, messages, markerPositions,
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
  vm.runInContext("controller.onRoadviewPositionChanged()", h.context);
  assert.equal(h.moves.length, 1, "programmatic panorama does not echo a movement");
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

test("QGIS zoom moves only map center and preserves panorama and marker", () => {
  const h = harness();
  vm.runInContext("moveViewer(128, 38, false)", h.context);
  assert.equal(h.mapCenters[0].getLng(), 128);
  assert.equal(h.lookups.length, 0);
  assert.equal(h.panos.length, 0);
  assert.equal(h.markerPositions.length, 0);
  assert.equal(h.moves.length, 0);
  h.dragEnd();
  assert.equal(h.lookups.length, 1, "pan after zoom must refresh Roadview");
});

test("zoom rejects an older pending panorama lookup", () => {
  const h = harness();
  vm.runInContext("moveViewer(128, 38); moveViewer(128.1, 38.1, false)", h.context);
  h.lookups[0].callback(444);
  assert.equal(h.panos.length, 0);
});

function wheelHarness() {
  const h = harness();
  let level = 4, callback, options;
  const changes = [], anchors = [];
  const container = {
    clientHeight: 300,
    addEventListener(name, handler, settings) {
      assert.equal(name, "wheel"); callback = handler; options = settings;
    },
    getBoundingClientRect: () => ({ left: 100, top: 50 }),
  };
  h.context.container = container;
  h.context.map.getLevel = () => level;
  h.context.map.setLevel = (value, settings) => { level = value; changes.push(settings); };
  h.context.map.getProjection = () => ({ coordsFromContainerPoint(point) {
    anchors.push([point.x, point.y]); return "cursor-coordinate";
  } });
  h.context.kakao.maps.Point = function (x, y) { this.x = x; this.y = y; };
  vm.runInContext("configureMapWheel(container)", h.context);
  return { h, changes, anchors, options, level: () => level,
    wheel(deltaY, deltaMode = 0, modifiers = {}) {
      let prevented = false, stopped = false;
      callback({ deltaY, deltaMode, clientX: 150, clientY: 75, ...modifiers,
        preventDefault() { prevented = true; },
        stopImmediatePropagation() { stopped = true; } });
      return [prevented, stopped];
    }
  };
}

test("plugin wheel zoom is cursor-anchored, single-handled, and never moves Roadview or QGIS", () => {
  const w = wheelHarness();
  assert.equal(w.options.capture, true);
  assert.equal(w.options.passive, false);
  assert.deepEqual(w.wheel(-120), [true, true]);
  assert.equal(w.level(), 3);
  assert.deepEqual(w.anchors, [[50, 25]]);
  assert.equal(w.changes[0].anchor, "cursor-coordinate");
  assert.equal(w.changes[0].animate, false);
  w.wheel(120);
  assert.equal(w.level(), 4);
  assert.equal(w.h.lookups.length, 0);
  assert.equal(w.h.moves.length, 0);
  assert.equal(w.h.markerPositions.length, 0);
});

test("Ctrl/Meta wheel preserves browser default and suppresses SDK map zoom", () => {
  const w = wheelHarness();
  assert.deepEqual(w.wheel(-120, 0, { ctrlKey: true }), [false, true]);
  assert.deepEqual(w.wheel(-120, 0, { metaKey: true }), [false, true]);
  assert.equal(w.level(), 4);
  assert.equal(w.changes.length, 0);
  assert.deepEqual(w.wheel(-120), [true, true]);
  assert.equal(w.level(), 3);
});

test("wheel handles trackpad accumulation, delta units, bounds and invalid input", () => {
  const w = wheelHarness();
  for (let i = 0; i < 3; i++) w.wheel(-10);
  assert.equal(w.level(), 4);
  w.wheel(-10);
  assert.equal(w.level(), 3);
  w.wheel(3, 1);
  assert.equal(w.level(), 4);
  w.wheel(1, 2);
  assert.equal(w.level(), 5);
  for (let i = 0; i < 30; i++) w.wheel(-120);
  assert.equal(w.level(), 1);
  for (let i = 0; i < 30; i++) w.wheel(120);
  assert.equal(w.level(), 14);
  assert.deepEqual(w.wheel(0), [false, false]);
  assert.deepEqual(w.wheel(NaN), [false, false]);
});

function zoomHarness() {
  const w = wheelHarness();
  let timer;
  const zooms = [];
  w.h.context.document = { getElementById: () => ({ clientWidth: 400, clientHeight: 300 }) };
  w.h.context.map.getProjection = () => ({ coordsFromContainerPoint(point) {
    const resolution = 0.00001 * 2 ** (w.level() - 4);
    return { getLat: () => 37, getLng: () => 127 + (point.x - 200) * resolution };
  } });
  w.h.context.window.setTimeout = (callback) => { timer = callback; return 1; };
  w.h.context.window.clearTimeout = () => { timer = null; };
  w.h.context.qgisBridge.zoomQgisView = (...args) => zooms.push(args);
  const originalSetLevel = w.h.context.map.setLevel;
  w.h.context.map.setLevel = (level, options) => {
    originalSetLevel(level, options);
    vm.runInContext('scheduleMapZoomSync()', w.h.context);
  };
  return { w, zooms, fire() { const fn = timer; timer = null; fn?.(); } };
}

test('QGIS resolution selects nearest Kakao level without echo or Roadview lookup', () => {
  const z = zoomHarness();
  const current = vm.runInContext('mapMetersPerPixel()', z.w.h.context);
  assert.ok(Math.abs(current - 0.88804) < 0.0001);
  z.w.h.context.resolution = current / 4;
  vm.runInContext('applyMapResolution(resolution)', z.w.h.context);
  assert.equal(z.w.level(), 2);
  z.fire();
  assert.equal(z.zooms.length, 0, 'programmatic zoom must not feed back');
  assert.equal(z.w.h.lookups.length, 0);
});

test('plugin wheel forwards final center and ground resolution, not a Roadview move', () => {
  const z = zoomHarness();
  z.w.wheel(-120);
  z.fire();
  assert.equal(z.zooms.length, 1);
  assert.deepEqual(z.zooms[0].slice(0, 2), [127, 37.5]);
  assert.ok(Math.abs(z.zooms[0][2] - 0.44402) < 0.0001);
  assert.equal(z.w.h.moves.length, 0);
  assert.equal(z.w.h.lookups.length, 0);
});

test('project reset cancels pending zoom and rejects an old panorama callback', () => {
  const z = zoomHarness();
  vm.runInContext('moveViewer(128, 38)', z.w.h.context);
  z.w.wheel(-120);
  vm.runInContext('controller.reset()', z.w.h.context);
  z.fire();
  z.w.h.lookups[0].callback(999);
  assert.equal(z.zooms.length, 0);
  assert.equal(z.w.h.panos.length, 0);
  z.w.h.dragEnd();
  z.w.h.lookups[1].callback(1000);
  assert.equal(z.w.h.panos[0].panoId, 1000, 'new work resumes after reset');
});

test('Roadview arrow movement updates map/marker and forwards position and direction', () => {
  const h = harness(), timers = new Map(), states = [];
  let next = 0;
  h.context.window.setTimeout = (fn, delay) => { timers.set(++next, { fn, delay }); return next; };
  h.context.window.clearTimeout = (id) => timers.delete(id);
  h.context.roadview.getPanoId = () => 321;
  h.context.roadview.getPosition = () => ({ getLng: () => 128, getLat: () => 38 });
  h.context.roadview.getViewpoint = () => ({ pan: 30, tilt: 5, zoom: 1 });
  h.context.qgisBridge.updateRoadviewState = (...args) => states.push(args);
  vm.runInContext('controller.onRoadviewPositionChanged()', h.context);
  assert.equal(h.mapCenters[0].getLng(), 128);
  assert.equal(h.markerPositions[0].getLat(), 38);
  assert.equal(h.lookups.length, 0);
  for (const { fn } of timers.values()) fn();
  assert.deepEqual(h.moves, [[128, 38]]);
  assert.deepEqual(states, [[128, 38, 30, 5, 1, '321']]);
});

test('reset cancels pending drag and Roadview-state timers without publishing', () => {
  const h = harness(), timers = new Map();
  let next = 0;
  h.context.window.setTimeout = (fn) => { timers.set(++next, fn); return next; };
  h.context.window.clearTimeout = (id) => timers.delete(id);
  vm.runInContext('controller.scheduleKakaoMapSync(); controller.scheduleRoadviewStateSync()', h.context);
  assert.equal(timers.size, 2);
  vm.runInContext('controller.reset()', h.context);
  assert.equal(timers.size, 0);
  assert.equal(h.moves.length, 0);
});
