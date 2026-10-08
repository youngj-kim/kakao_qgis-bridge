const assert = require("node:assert/strict");
const { test } = require("node:test");
const { Element, loadController, createDocument } = require("./viewer_test_support");

function harness(connected = true) {
  const routeHistoryList = new Element();
  const calls = [], cleared = [], messages = [];
  const bridge = Object.fromEntries(["selectRouteHistory", "loadRouteHistory", "deleteRouteHistory",
    "exportRouteHistory", "loadRouteHistoryFile", "deleteAllRouteHistories", "exportRouteHistories"]
    .map((method) => [method, (...args) => calls.push([method, ...args])]));
  const controller = loadController("history").createKakaoHistoryController({
    document: createDocument(), routeHistoryList, getBridge: () => connected ? bridge : null,
    getActiveTab: () => "history", setStatus: (message) => messages.push(message),
    renderRouteGuidance: (payload) => cleared.push(payload),
    formatGuidanceDistance: (distance) => distance + " m", formatGuidanceDuration: (duration) => duration + "초",
    activateRoutePanelTab() {}, updateRouteControls() {}, updateRoutePanelVisibility() {}, scheduleStableRelayout() {}
  });
  return { controller, routeHistoryList, calls, cleared, messages };
}
const items = [
  { history_id: "a", origin_name: "<출발 & A>", destination_name: "도착", distance_m: 100, duration_s: 60 },
  { history_id: "b", origin_name: "B", destination_name: "C", result_summary: "요약" }
];
function checkbox(h, index) { return h.routeHistoryList.children[index + 1].children[0]; }

test("history renders safe text, keyboard selection and per-history bridge actions", () => {
  const h = harness();
  h.controller.render({ items, selected_history_id: "a" });
  assert.equal(h.controller.count, 2);
  assert.equal(h.controller.activeId, "a");
  assert.match(h.routeHistoryList.textContent, /<출발 & A>/);
  h.routeHistoryList.children[2].fire("keydown", { key: "Enter" });
  assert.equal(h.controller.activeId, "b");
  assert.deepEqual(h.calls[0], ["selectRouteHistory", "b"]);
  const actions = h.routeHistoryList.children[1].children[1].children[3];
  actions.children.forEach((button) => button.fire("click"));
  assert.deepEqual(h.calls.slice(1), [["loadRouteHistory", "a"], ["deleteRouteHistory", "a"], ["exportRouteHistory", "a"]]);
});
test("bulk selection, export, deselection and stale-ID pruning stay consistent", () => {
  const h = harness();
  h.controller.render({ items });
  checkbox(h, 0).checked = true;
  checkbox(h, 0).fire("change");
  assert.equal(h.controller.selectedIds().join(), "a");
  h.routeHistoryList.children[0].children[4].fire("click");
  assert.deepEqual(h.calls[0], ["exportRouteHistories", '["a"]']);
  h.routeHistoryList.children[0].children[2].fire("click");
  assert.equal(h.controller.selectedIds().join(), "a,b");
  h.controller.render({ items: [items[1]] });
  assert.equal(h.controller.selectedIds().join(), "b");
  h.routeHistoryList.children[0].children[2].fire("click");
  assert.equal(h.controller.selectedIds().length, 0);
});
test("removing active history clears guidance and empty lists disable bulk actions", () => {
  const h = harness();
  h.controller.render({ items, selected_history_id: "a" });
  h.controller.render({ items: [] });
  assert.equal(h.controller.activeId, "");
  assert.equal(h.cleared.length, 1);
  assert.equal(h.cleared[0].guides.length, 0);
  assert.match(h.routeHistoryList.textContent, /아직/);
  for (const index of [2, 3, 4]) assert.equal(h.routeHistoryList.children[0].children[index].disabled, true);
});
test("bulk import/delete use current bridge and disconnected actions show status", () => {
  const h = harness();
  h.controller.render({ items });
  h.routeHistoryList.children[0].children[1].fire("click");
  h.routeHistoryList.children[0].children[3].fire("click");
  assert.deepEqual(h.calls, [["loadRouteHistoryFile"], ["deleteAllRouteHistories"]]);
  const offline = harness(false);
  offline.controller.render(null);
  offline.routeHistoryList.children[0].children[1].fire("click");
  assert.match(offline.messages[0], /사용할 수 없습니다/);
});
