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
      element.style = { setProperty(name, value) { this[name] = value; } };
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
  test(mode + " native dock relayout hook retains inputs and queues view resizing", () => {
    const h = harness(mode);
    h.node("route-origin-input").value = "서울역";
    const calls = h.calls.slice();
    let requests = 0;
    h.window.setTimeout = () => { requests += 1; return requests; };
    h.window.relayoutKakaoViewer();
    assert.equal(requests, 4);
    assert.equal(h.node("route-origin-input").value, "서울역");
    assert.deepEqual(h.calls, calls);
  });
  test(mode + " vertical split uses remaining space weights, not full window percentages", () => {
    const h = harness(mode);
    vm.runInContext("applyViewerSplit(60)", h.context);
    const style = h.node("viewer").style;
    assert.equal(style["--split-primary-size"], "60%");
    assert.equal(style["--split-primary-weight"], "60fr");
    assert.equal(style["--split-secondary-weight"], "40fr");
    vm.runInContext("applyViewerSplit(200)", h.context);
    assert.equal(style["--split-primary-weight"], "70fr");
    assert.equal(style["--split-secondary-weight"], "30fr");
  });
  test(mode + " explorer collapses the whole panel without clearing inputs or results", () => {
    const h = harness(mode);
    const body = h.node("explorer-body"), toggle = h.node("explorer-toggle");
    h.node("route-origin-input").value = "서울역";
    h.node("route-destination-input").value = "수원역";
    h.node("search-query").value = "서울";
    h.node("map-type").value = "HYBRID";
    h.signals.routeGuidanceChanged(JSON.stringify({
      guides: [{ sequence: 1, longitude: 127, latitude: 37.5, guidance: "안내 유지" }],
      path: [], summary: { duration_s: 60, distance_m: 100 }
    }));
    const guidance = h.node("route-guidance-list").textContent;
    const calls = h.calls.slice();
    let relayoutRequests = 0;
    h.window.setTimeout = () => { relayoutRequests += 1; return relayoutRequests; };
    toggle.fire("click");
    assert.equal(body.hidden, true);
    assert.equal(toggle.attributes["aria-expanded"], "false");
    assert.match(toggle.textContent, /Expand/);
    assert.equal(relayoutRequests, 4);
    toggle.fire("click");
    assert.equal(body.hidden, false);
    assert.equal(toggle.attributes["aria-expanded"], "true");
    assert.match(toggle.textContent, /Collapse/);
    assert.equal(relayoutRequests, 8);
    assert.equal(h.node("route-origin-input").value, "서울역");
    assert.equal(h.node("route-destination-input").value, "수원역");
    assert.equal(h.node("search-query").value, "서울");
    assert.equal(h.node("map-type").value, "HYBRID");
    assert.equal(h.node("route-guidance-list").textContent, guidance);
    assert.deepEqual(h.calls, calls, "Collapsing must not send route/bridge commands");
  });
  test("assembled " + mode + " page initializes controllers and handles bridge signals without SDK", () => {
    const h = harness(mode);
    assert.match(h.node("status").textContent, /API 키/);
    assert.equal(h.node("map-type").disabled, true);
    assert.equal(h.node("roadview-roads-toggle").disabled, true);
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
    assert.match(h.node("status").textContent, /프로젝트가 변경되어 현재 표시와 입력/);
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
