/* Map appearance only: never change center, zoom, route or Roadview position. */
(function () {
  "use strict";
  window.createKakaoMapOptions = function (deps) {
    const { typeSelect, roadsButton, getMap, getMaps } = deps;
    const allowedTypes = new Set(["ROADMAP", "SKYVIEW", "HYBRID"]);
    let ready = false;
    let showRoads = false;
    typeSelect.disabled = true;
    roadsButton.disabled = true;
    roadsButton.setAttribute("aria-pressed", "false");

    typeSelect.addEventListener("change", function () {
      if (!ready) return;
      const type = allowedTypes.has(typeSelect.value) ? typeSelect.value : "ROADMAP";
      typeSelect.value = type;
      getMap().setMapTypeId(getMaps().MapTypeId[type]);
    });
    roadsButton.addEventListener("click", function () {
      if (!ready) return;
      const map = getMap();
      const overlay = getMaps().MapTypeId.ROADVIEW;
      if (showRoads) map.removeOverlayMapTypeId(overlay);
      else map.addOverlayMapTypeId(overlay);
      showRoads = !showRoads;
      roadsButton.setAttribute("aria-pressed", String(showRoads));
      roadsButton.textContent = showRoads ? "Hide Roadview roads" : "Show Roadview roads";
    });
    return {
      initialize() {
        if (ready || !getMap()) return;
        ready = true;
        typeSelect.value = "ROADMAP";
        typeSelect.disabled = false;
        roadsButton.disabled = false;
      }
    };
  };
})();
