const assert = require("node:assert/strict");
const { test } = require("node:test");
const { Element, loadController } = require("./viewer_test_support");

function harness() {
  const typeSelect = new Element("select");
  const roadsButton = new Element("button");
  const calls = [];
  // No center/zoom/Roadview APIs: accidental position changes fail the test.
  const map = {
    setMapTypeId: (id) => calls.push(["type", id]),
    addOverlayMapTypeId: (id) => calls.push(["add", id]),
    removeOverlayMapTypeId: (id) => calls.push(["remove", id])
  };
  let available = false;
  const controller = loadController("map_options").createKakaoMapOptions({
    typeSelect, roadsButton, getMap: () => available ? map : null,
    getMaps: () => {
      assert.equal(available, true);
      return { MapTypeId: { ROADMAP: 1, SKYVIEW: 2, HYBRID: 3, ROADVIEW: 8 } };
    }
  });
  return { typeSelect, roadsButton, calls, controller,
    initialize() { available = true; controller.initialize(); },
    select(value) { typeSelect.value = value; typeSelect.fire("change"); } };
}

test("map controls wait for SDK readiness", () => {
  const h = harness();
  h.controller.initialize();
  h.select("HYBRID");
  h.roadsButton.fire("click");
  assert.equal(h.typeSelect.disabled, true);
  assert.equal(h.roadsButton.disabled, true);
  assert.deepEqual(h.calls, []);
  h.initialize();
  assert.equal(h.typeSelect.disabled, false);
  assert.equal(h.roadsButton.disabled, false);
  assert.equal(h.typeSelect.value, "ROADMAP");
});

test("three map types change appearance only; unknown types fall back safely", () => {
  const h = harness();
  h.initialize();
  for (const value of ["SKYVIEW", "HYBRID", "ROADMAP", "ROADVIEW", "toString"]) h.select(value);
  assert.deepEqual(h.calls, [["type", 2], ["type", 3], ["type", 1], ["type", 1], ["type", 1]]);
  assert.equal(h.typeSelect.value, "ROADMAP");
});

test("coverage toggles independently of imagery and repeated initialization", () => {
  const h = harness();
  h.initialize();
  h.roadsButton.fire("click");
  assert.equal(h.roadsButton.attributes["aria-pressed"], "true");
  assert.match(h.roadsButton.textContent, /Hide/);
  h.select("HYBRID");
  h.controller.initialize();
  assert.equal(h.typeSelect.value, "HYBRID");
  assert.equal(h.roadsButton.attributes["aria-pressed"], "true");
  h.roadsButton.fire("click");
  assert.equal(h.roadsButton.attributes["aria-pressed"], "false");
  assert.match(h.roadsButton.textContent, /Show/);
  assert.deepEqual(h.calls, [["add", 8], ["type", 3], ["remove", 8]]);
});
