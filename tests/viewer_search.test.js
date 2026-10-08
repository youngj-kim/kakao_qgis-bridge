const assert = require("node:assert/strict");
const { test } = require("node:test");
const { Element, loadController, createDocument } = require("./viewer_test_support");

function harness(ready = true) {
  const nodes = Object.fromEntries(["searchForm", "searchQuery", "searchSubmit", "searchClear", "searchResults"]
    .map((name) => [name, new Element()]));
  const places = [], addresses = [], selected = [], messages = [];
  const services = ready ? {
    placesService: { keywordSearch(query, callback) { places.push({ query, callback }); } },
    geocoderService: { addressSearch(query, callback) { addresses.push({ query, callback }); } },
    status: { OK: "OK", ERROR: "ERROR" }
  } : {};
  const controller = loadController("search").createKakaoSearchController({
    ...nodes, document: createDocument(), getServices: () => services,
    setStatus: (message) => messages.push(message), selectSearchResult: (result) => selected.push(result)
  });
  return { ...nodes, controller, places, addresses, selected, messages };
}
const place = { place_name: "<서울 & 역>", address_name: "서울", x: "127", y: "37.5" };

test("search combines both SDK replies, removes duplicates/invalid coordinates and uses safe text", () => {
  const h = harness();
  h.controller.search("서울");
  h.places[0].callback([place, place, { ...place, x: "invalid" }], "OK");
  assert.equal(h.searchResults.children.length, 0);
  h.addresses[0].callback([{ address_name: "주소", x: "128", y: "38" }], "OK");
  assert.equal(h.searchResults.children.length, 2);
  assert.equal(h.searchResults.children[0].children[0].textContent, "<서울 & 역>");
  h.searchResults.children[0].fire("click");
  assert.equal(h.selected[0].lon, 127);
  assert.equal(h.searchSubmit.disabled, false);
});
test("new search and cancellation reject late SDK replies and release controls", () => {
  const h = harness();
  h.controller.search("old");
  h.controller.search("new");
  h.places[0].callback([place], "OK");
  h.addresses[0].callback([], "OK");
  assert.equal(h.searchResults.children.length, 0);
  assert.equal(h.searchSubmit.disabled, true);
  h.controller.cancel();
  h.places[1].callback([place], "OK");
  h.addresses[1].callback([], "OK");
  assert.equal(h.searchResults.children.length, 0);
  assert.equal(h.searchResults.hidden, true);
  assert.equal(h.searchSubmit.disabled, false);
});
test("route input selects first match without rendering or managing main search button", () => {
  const h = harness(), results = [];
  h.searchSubmit.disabled = true;
  h.controller.search("route", (result) => results.push(result), false, true);
  h.addresses[0].callback([], "ZERO_RESULT");
  h.places[0].callback([place], "OK");
  assert.equal(results.length, 1);
  assert.equal(h.searchResults.hidden, true);
  assert.equal(h.searchSubmit.disabled, true);
});
test("failure and unavailable SDK show status without a selection", () => {
  const h = harness();
  h.controller.search("missing");
  h.places[0].callback([], "ERROR");
  h.addresses[0].callback([], "ERROR");
  assert.match(h.messages.at(-1), /실패/);
  assert.match(h.searchResults.textContent, /없습니다/);
  const unavailable = harness(false);
  unavailable.controller.search("x");
  unavailable.controller.cancel();
  assert.match(unavailable.messages[0], /준비/);
  assert.equal(unavailable.searchSubmit.disabled, true);
});
test("form, escape and clear handlers preserve keyboard/cancellation behavior", () => {
  const h = harness();
  h.searchForm.fire("submit");
  assert.equal(h.searchQuery.focused, true);
  h.searchQuery.value = "서울";
  h.searchForm.fire("submit");
  assert.equal(h.places[0].query, "서울");
  h.searchQuery.fire("keydown", { key: "Escape" });
  assert.equal(h.searchResults.hidden, true);
  h.searchClear.fire("click");
  assert.equal(h.searchQuery.value, "");
  h.places[0].callback([place], "OK");
  h.addresses[0].callback([], "OK");
  assert.equal(h.searchResults.children.length, 0);
});
