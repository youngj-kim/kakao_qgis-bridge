const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");
const { Element, createDocument } = require("./viewer_test_support");

function harness(mode) {
  const web = path.join(__dirname, "..", "kakao_qgis_bridge", "web");
  const html = fs.readFileSync(path.join(web, "kakao_viewer.html"), "utf8")
    .replace(/__VIEWER_([A-Z_]+)_SCRIPT__/g, (_, name) =>
      fs.readFileSync(path.join(web, "viewer_" + name.toLowerCase() + ".js"), "utf8"))
    .replace("__KAKAO_APP_KEY_JSON__", '""');
  const nodes = new Map(), signals = {}, calls = [];
  function node(id) {
    if (!nodes.has(id)) {
      const element = new Element();
      element.style = { setProperty() {} };
      element.options = [{ text: "fixture" }];
      element.selectedIndex = 0;
      element.querySelector = () => null;
      nodes.set(id, element);
    }
    return nodes.get(id);
  }
  const document = {
    ...createDocument(), getElementById: node, addEventListener() {},
    documentElement: new Element()
  };
  const bridge = {
    start() { calls.push("start"); }, clearRoutePoints() { calls.push("clearRoutePoints"); },
    setRoutePoint() {},
    refreshRouteHistory() { calls.push("refreshRouteHistory"); }
  };
  for (const name of ["routeStatusChanged", "routeGuidanceChanged", "routeHistoryChanged",
    "loadRouteHistoryInput", "projectReset"]) {
    bridge[name] = { connect: (callback) => { signals[name] = callback; } };
  }
  const window = {
    setTimeout() { return 1; }, clearTimeout() {}, addEventListener() {},
    matchMedia: () => ({ matches: false }), localStorage: { getItem: () => null, setItem() {} }
  };
  const context = vm.createContext({
    document, window, console,
    ...(mode === "external" ? {} : {
      qt: { webChannelTransport: {} },
      QWebChannel: function (_transport, callback) { callback({ objects: { qgisBridge: bridge } }); }
    })
  });
  if (mode === "external") window.kakaoExternalBridge = bridge;
  else {
    window.qt = context.qt;
    window.QWebChannel = context.QWebChannel;
  }
  for (const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)) {
    if (match[1].trim()) vm.runInContext(match[1], context);
  }
  return { node, signals, calls, window, context };
}

for (const mode of ["external", "dock"]) {
  test("assembled " + mode + " page initializes controllers and handles bridge signals without SDK", () => {
    const h = harness(mode);
    assert.match(h.node("status").textContent, /API 키/);
    h.signals.routeGuidanceChanged(JSON.stringify({
      guides: [{ sequence: 1, longitude: 127, latitude: 37.5, guidance: "안내" }],
      path: [], summary: { duration_s: 60, distance_m: 100 }
    }));
    assert.match(h.node("route-guidance-list").textContent, /안내/);
    h.signals.routeHistoryChanged(JSON.stringify({
      selected_history_id: "a", items: [{ history_id: "a", origin_name: "출발", destination_name: "도착" }]
    }));
    assert.match(h.node("route-history-list").textContent, /출발/);
    h.node("route-history-tab").fire("click");
    assert.equal(h.node("route-history-list").hidden, false);
    assert.equal(h.node("route-guidance-list").hidden, true);
    h.signals.routeHistoryChanged(JSON.stringify({ items: [] }));
    assert.equal(h.node("route-guidance-list").children.length, 0);
    h.node("route-origin-input").value = "old";
    h.signals.projectReset(1);
    assert.equal(h.node("route-origin-input").value, "");
    assert.equal(h.calls.includes("clearRoutePoints"), false, "Reset must not echo to bridge");
    h.node("route-origin-input").value = "new";
    h.signals.projectReset(1);
    assert.equal(h.node("route-origin-input").value, "new");
    h.signals.routeGuidanceChanged("invalid-json");
    h.signals.routeHistoryChanged("invalid-json");
    assert.match(h.node("status").textContent, /표시하지 못했습니다/);
    h.window.centerKakaoMap(127, 37.5);
    assert.match(h.node("status").textContent, /준비 대기/);
  });
}
