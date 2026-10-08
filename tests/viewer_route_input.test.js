const assert = require("node:assert/strict");
const { test } = require("node:test");
const { Element, loadController, createDocument } = require("./viewer_test_support");

function harness(connected = true) {
  const ui = Object.fromEntries(["routeOriginInput","routeDestinationInput","routeOriginCurrentButton","routeDestinationCurrentButton","routePrioritySelect","routeAvoidToggle","routeAvoidOptions","routeAvoidCheckboxes","routeVehicleToggle","routeVehicleOptions","routeCarType","routeCarFuel","routeCarHipass","routeAddWaypointButton","routeWaypointsContainer","routeCreateButton","routeHistoryOpenButton","routeSwapButton","routeResetButton","searchResults"].filter((n) => n !== "routeAvoidCheckboxes")
    .map((name) => [name, new Element()]));
  ui.routeAvoidCheckboxes = [];
  for (const control of [ui.routeCarType, ui.routeCarFuel, ui.routePrioritySelect]) {
    control.options = [{ text: "fixture" }]; control.selectedIndex = 0;
    control.querySelector = () => true;
  }
  ui.routeCarType.value = "1"; ui.routeCarFuel.value = "GASOLINE";
  ui.routePrioritySelect.value = "RECOMMEND";
  const calls = [], messages = [], places = [], addresses = [], timers = new Map();
  let timerId = 0;
  const bridge = Object.fromEntries(["setRoutePoint", "clearRoutePoint", "clearRoutePoints", "moveQgisCenter", "requestRoute"]
    .map((method) => [method, (...args) => calls.push([method, ...args])]));
  const services = {
    placesService: { keywordSearch(query, callback) { places.push({ query, callback }); } },
    geocoderService: { addressSearch(query, callback) { addresses.push({ query, callback }); } },
    status: { OK: "OK" }
  };
  const controller = loadController("route_input").createKakaoRouteInputController({
    document: createDocument(), ui, maxRouteWaypoints: 5,
    getMap: () => ({ getCenter: () => ({ getLng: () => 127, getLat: () => 37.5 }), setLevel() {} }),
    getBridge: () => connected ? bridge : null, getServices: () => services,
    search() {}, cancelSearch() {},
    timers: { setTimeout(callback) { timers.set(++timerId, callback); return timerId; },
      clearTimeout(id) { timers.delete(id); } },
    moveViewer() {}, setStatus: (message) => messages.push(message),
    formatCoordinate: ({ lon, lat }) => lon.toFixed(7) + ", " + lat.toFixed(7),
    routeInputLabel: (location, fallback) => location.label || fallback,
    clearRoutePath() {}
  });
  return { ui, controller, calls, messages, places, addresses, timers, bridge };
}
function coordinates(h) {
  h.ui.routeOriginInput.value = "127, 37.5";
  h.ui.routeDestinationInput.value = "128, 38";
}
function finish(h, index, found = true) {
  const data = found ? [{ x: "127", y: "37.5" }] : [];
  h.addresses[index].callback(data, found ? "OK" : "ZERO_RESULT");
  h.places[index].callback([], "ZERO_RESULT");
}

test("coordinate parser supports both orders and rejects out-of-range/malformed input", () => {
  const h = harness();
  assert.equal(h.controller.parseCoordinate("37.5 127").lon, 127);
  assert.equal(h.controller.parseCoordinate("127,37.5").lat, 37.5);
  for (const text of ["181,37", "127,91", "x,y", "127,", "1 2 3"]) {
    assert.equal(h.controller.parseCoordinate(text), null);
  }
});
test("waypoints retain IDs/order after movement/deletion and enforce the maximum", () => {
  const h = harness();
  for (let i = 0; i < 6; i++) h.controller.addWaypoint();
  assert.equal(h.controller.waypointCount, 5);
  const first = h.ui.routeWaypointsContainer.children[0];
  first.children[3].children[1].fire("click");
  assert.equal(h.ui.routeWaypointsContainer.children[1], first);
  first.children[4].fire("click");
  assert.equal(h.controller.waypointCount, 4);
  assert.deepEqual(h.calls.at(-1), ["clearRoutePoint", "waypoint:1"]);
  assert.equal(h.ui.routeWaypointsContainer.children[0].children[0].textContent, "경유 1");
});
test("coordinate request preserves serialized options/waypoints and suppresses duplicate clicks", async () => {
  const h = harness(); coordinates(h);
  h.controller.addWaypoint();
  h.ui.routeWaypointsContainer.children[0].children[1].value = "127.5, 37.7";
  const pending = h.controller.request();
  await h.controller.request();
  await pending;
  const requests = h.calls.filter((call) => call[0] === "requestRoute");
  assert.equal(requests.length, 1);
  assert.deepEqual(requests[0].slice(1, 6), [127, 37.5, 128, 38, "RECOMMEND"]);
  assert.equal(JSON.parse(requests[0][6])[0].id, "waypoint:1");
  assert.equal(JSON.parse(requests[0][8]).car_type, 1);
  assert.equal(h.controller.busy, true);
  h.controller.complete();
  assert.equal(h.controller.busy, false);
  assert.equal(h.ui.routeCreateButton.disabled, false);
});
test("reset cancels pending geocoding and never publishes an old route or echoes a clear", async () => {
  const h = harness(); coordinates(h); h.ui.routeOriginInput.value = "old-address";
  const pending = h.controller.request();
  h.controller.reset();
  assert.equal(h.controller.busy, false);
  assert.equal(h.ui.routeOriginInput.value, "");
  finish(h, 0);
  await pending;
  assert.equal(h.calls.length, 0);
});
test("old lookup failure cannot overwrite the status or busy state of a new request", async () => {
  const h = harness(); coordinates(h); h.ui.routeOriginInput.value = "old";
  const old = h.controller.request();
  h.controller.reset(); coordinates(h); h.ui.routeOriginInput.value = "new";
  const current = h.controller.request();
  const message = h.messages.at(-1);
  finish(h, 0, false);
  await old;
  assert.equal(h.controller.busy, true);
  assert.equal(h.messages.at(-1), message);
  finish(h, 1);
  await current;
  assert.equal(h.calls.filter((call) => call[0] === "requestRoute").length, 1);
});
test("lookup and synchronous transport failures release controls without a success state", async () => {
  const h = harness(); coordinates(h); h.ui.routeOriginInput.value = "missing";
  const pending = h.controller.request();
  finish(h, 0, false);
  await pending;
  assert.equal(h.controller.busy, false);
  assert.match(h.messages.at(-1), /찾지 못했습니다/);
  coordinates(h);
  h.bridge.requestRoute = () => { throw new Error("transport unavailable"); };
  await h.controller.request();
  assert.equal(h.controller.busy, false);
  assert.equal(h.messages.at(-1), "transport unavailable");
});
test("history restore keeps input/vehicle options and cancels pending location work", async () => {
  const h = harness(); coordinates(h); h.ui.routeOriginInput.value = "old";
  const old = h.controller.request();
  h.controller.load({
    origin: { label: "saved origin", lon: 129, lat: 36 },
    destination: { label: "saved destination", lon: 130, lat: 35 },
    waypoints: [{ label: "saved waypoint", lon: 129.5, lat: 35.5 }],
    priority: "TIME", vehicle: { car_type: 2, car_fuel: "DIESEL", car_hipass: true }
  });
  finish(h, 0); await old;
  assert.equal(h.ui.routeOriginInput.value, "saved origin");
  assert.equal(h.controller.waypointCount, 1);
  assert.equal(h.ui.routeCarType.value, "2");
  assert.equal(h.calls.filter((call) => call[0] === "requestRoute").length, 0);
});
test("input debounce is canceled by reset and disconnected request gives status", async () => {
  const h = harness();
  h.ui.routeOriginInput.value = "address";
  h.ui.routeOriginInput.fire("input");
  assert.equal(h.timers.size, 1);
  h.controller.reset();
  assert.equal(h.timers.size, 0);
  const offline = harness(false); coordinates(offline);
  await offline.controller.request();
  assert.match(offline.messages.at(-1), /준비되지 않았습니다/);
});

test("invalid SDK coordinates are skipped in favor of a valid place or rejected", async () => {
  const h = harness(); coordinates(h); h.ui.routeOriginInput.value = "lookup";
  const pending = h.controller.request();
  h.addresses[0].callback([{ x: "NaN", y: "37.5" }], "OK");
  h.places[0].callback([{ x: "127", y: "37.5" }], "OK");
  await pending;
  assert.equal(h.calls.find((call) => call[0] === "requestRoute")[1], 127);
  h.controller.reset(); coordinates(h); h.ui.routeOriginInput.value = "bad";
  const invalid = h.controller.request();
  h.addresses[1].callback([{ x: "181", y: "37.5" }], "OK");
  h.places[1].callback([{ x: "127", y: "91" }], "OK");
  await invalid;
  assert.equal(h.controller.busy, false);
  assert.match(h.messages.at(-1), /찾지 못했습니다/);
});
