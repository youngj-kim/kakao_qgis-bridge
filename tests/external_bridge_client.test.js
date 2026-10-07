const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const python = fs.readFileSync(path.join(__dirname, "..", "kakao_qgis_bridge", "external_bridge.py"), "utf8");
const source = python.match(/EXTERNAL_BRIDGE_SCRIPT = r"""([\s\S]*?)"""/)[1]
  .replace(/<\/?script>/g, "").replace("__KAKAO_BRIDGE_TOKEN_JSON__", '"test-token"');

function harness() {
  const timers = new Map();
  const calls = [];
  const centers = [];
  const messages = [];
  let timerId = 0;
  const queue = [];
  const window = {
    crypto: { randomUUID: () => "tab-a" },
    centerKakaoMap: (lon, lat) => centers.push([lon, lat]),
    setKakaoBridgeStatus: (message) => messages.push(message),
  };
  const context = {
    window, document: { documentElement: { classList: { add() {} } } },
    AbortController, console: { warn() {} },
    setTimeout(fn, delay) { timers.set(++timerId, { fn, delay }); return timerId; },
    clearTimeout(id) { timers.delete(id); },
    async fetch(url, options) {
      calls.push({ url, options });
      assert.ok(queue.length, `Unexpected fetch ${url}`);
      const response = queue.shift();
      return typeof response === "function" ? response() : response;
    },
  };
  vm.runInNewContext(source, context);
  const bridge = window.kakaoExternalBridge;
  return {
    bridge, calls, centers, messages, timers,
    respond(payload, status = 200) {
      queue.push({ ok: status < 400, status, json: async () => payload });
    },
    defer(response) { queue.push(response); },
    async tick(delay) {
      const timer = [...timers.entries()].find(([, value]) => value.delay === delay);
      assert.ok(timer, `No timer with delay ${delay}`);
      timers.delete(timer[0]);
      await timer[1].fn();
    },
  };
}

test("new tab starts from snapshot and applies route before center", async () => {
  const h = harness();
  const order = [];
  h.bridge.routeGuidanceChanged.connect(() => order.push("guidance"));
  h.bridge.routeHistoryChanged.connect(() => order.push("history"));
  h.bridge.loadRouteHistoryInput.connect(() => assert.fail("Old input command replayed"));
  h.respond({ sequence: 20, signals: {
    routeGuidanceChanged: { args: ["current-route"] },
    routeHistoryChanged: { args: ["selected-history"] },
  }, center: { lon: 127, lat: 37.5, sequence: 19 } });
  assert.equal(h.calls.length, 0);
  h.bridge.start();
  h.bridge.start();
  assert.equal(h.timers.size, 1);
  await h.tick(0);
  assert.deepEqual(order, ["guidance", "history"]);
  assert.deepEqual(h.centers, [[127, 37.5]]);
  assert.equal(h.calls[0].url, "/api/state");
  h.respond({ events: [], sequence: 20, resync_required: false });
  await h.tick(400);
  assert.equal(h.calls[1].url, "/api/events?since=20");
});

test("tab ignores its own movement but follows another tab", async () => {
  const h = harness();
  h.respond({ sequence: 0, signals: {}, center: null });
  h.bridge.start();
  await h.tick(0);
  h.respond({ events: [
    { sequence: 1, signal: "centerChanged", center: { sequence: 1, lon: 127, lat: 37.5, source: "tab-a" } },
    { sequence: 2, signal: "centerChanged", center: { sequence: 2, lon: 128, lat: 38, source: "tab-b" } },
  ] });
  await h.tick(400);
  assert.deepEqual(h.centers, [[128, 38]]);
  assert.equal(h.calls[1].options.headers["X-Kakao-Bridge-Client"], "tab-a");
});

test("event gap restores snapshot without replaying old commands", async () => {
  const h = harness();
  let route = "";
  h.bridge.routeGuidanceChanged.connect((value) => { route = value; });
  h.bridge.loadRouteHistoryInput.connect(() => assert.fail("Old command replayed"));
  h.respond({ sequence: 1, signals: {}, center: { sequence: 1, lon: 127, lat: 37.5 } });
  h.bridge.start();
  await h.tick(0);
  h.respond({ resync_required: true, snapshot: {
    sequence: 200, center: { sequence: 1, lon: 127, lat: 37.5 },
    signals: { routeGuidanceChanged: { args: ["latest-route"] } },
  } });
  await h.tick(400);
  assert.equal(route, "latest-route");
  // Center is reapplied even when unchanged, after route bounds were fitted.
  assert.equal(h.centers.length, 2);
  h.respond({ events: [] });
  await h.tick(400);
  assert.equal(h.calls[2].url, "/api/events?since=200");
});

test("polling waits for response and backs off after HTTP failure", async () => {
  const h = harness();
  let finish;
  h.defer(() => new Promise((resolve) => { finish = resolve; }));
  h.bridge.start();
  const pending = h.tick(0);
  await Promise.resolve();
  assert.equal(h.calls.length, 1);
  assert.deepEqual([...h.timers.values()].map((timer) => timer.delay), [10000]);
  finish({ ok: false, status: 503, json: async () => ({}) });
  await pending;
  h.respond({ sequence: 10, signals: {}, center: null });
  await h.tick(800);
  h.respond({ events: [] });
  await h.tick(400);
  assert.equal(h.calls.length, 3);
});

test("failed route POST releases busy state through failure signal", async () => {
  const h = harness();
  const failures = [];
  h.bridge.routeStatusChanged.connect((ok, message) => failures.push({ ok, message }));
  h.respond({}, 503);
  h.bridge.requestRoute(127, 37.5, 128, 38, "RECOMMEND", "[]", "[]", "{}", "", "");
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(failures.length, 1);
  assert.equal(failures[0].ok, false);
  assert.match(failures[0].message, /503/);
});
