/* Map/Roadview synchronization and timers, independent of page UI/layout. */
window.createKakaoViewerSync = function createKakaoViewerSync({
  document, timers: window, getMap, getMarker, getRoadview, getRoadviewClient,
  getMaps, getBridge, setStatus
}) {
    let moveRequestId = 0;
    let mapSyncTimer = null, roadviewSyncTimer = null, roadviewStateTimer = null;
    let programmaticRoadviewPanoId = null, expectedMapZoomLevel = null, mapZoomSyncTimer = null;

    function syncKakaoMapToQgis(updateRoadview = false) {
      const map = getMap(), marker = getMarker(), roadview = getRoadview();
      const roadviewClient = getRoadviewClient(), qgisBridge = getBridge();
      const position = map.getCenter();
      const lat = position.getLat();
      const lon = position.getLng();
      marker.setPosition(position);
      // Update locally on drag end; this tab does not receive its own echo.
      if (updateRoadview && roadviewClient && roadview) {
        updateRoadviewPosition(position);
      }

      if (!qgisBridge) {
        setStatus("카카오 지도 위치를 QGIS에 전달할 연결이 아직 준비되지 않았습니다.");
        return;
      }

      qgisBridge.moveQgisCenter(lon, lat);
      setStatus(`카카오 지도 → QGIS EPSG:4326 ${lat.toFixed(6)}, ${lon.toFixed(6)}`);
    }

    function scheduleKakaoMapSync() {
      if (mapSyncTimer !== null) {
        return;
      }

      mapSyncTimer = window.setTimeout(() => {
        mapSyncTimer = null;
        syncKakaoMapToQgis();
      }, 120);
    }

    function syncRoadviewStateToQgis() {
      const roadview = getRoadview(), qgisBridge = getBridge();
      if (!qgisBridge || !roadview) {
        return;
      }

      const position = roadview.getPosition();
      const viewpoint = roadview.getViewpoint();
      if (!position || !viewpoint) {
        return;
      }

      const lon = position.getLng();
      const lat = position.getLat();
      const pan = Number(viewpoint.pan);
      const tilt = Number(viewpoint.tilt);
      const zoom = Number(viewpoint.zoom);
      if (![lon, lat, pan, tilt, zoom].every(Number.isFinite)) {
        return;
      }

      const panoId = roadview.getPanoId();
      qgisBridge.updateRoadviewState(
        lon,
        lat,
        pan,
        tilt,
        zoom,
        panoId === null || panoId === undefined ? "" : String(panoId)
      );
    }

    function scheduleRoadviewStateSync() {
      if (roadviewStateTimer !== null) {
        return;
      }

      roadviewStateTimer = window.setTimeout(() => {
        roadviewStateTimer = null;
        syncRoadviewStateToQgis();
      }, 100);
    }

    function mapMetersPerPixel() {
      const map = getMap(), kakao = { maps: getMaps() };
      const container = document.getElementById("map");
      const projection = map.getProjection();
      const x = container.clientWidth / 2;
      const y = container.clientHeight / 2;
      const first = projection.coordsFromContainerPoint(new kakao.maps.Point(x - 64, y));
      const last = projection.coordsFromContainerPoint(new kakao.maps.Point(x + 64, y));
      const radians = (degrees) => degrees * Math.PI / 180;
      const phi1 = radians(first.getLat()), phi2 = radians(last.getLat());
      const a = Math.sin((phi2 - phi1) / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2)
        * Math.sin(radians(last.getLng() - first.getLng()) / 2) ** 2;
      return 6371008.8 * 2 * Math.asin(Math.sqrt(Math.min(1, Math.max(0, a)))) / 128;
    }

    function applyMapResolution(metersPerPixel) {
      const map = getMap();
      if (!Number.isFinite(metersPerPixel) || metersPerPixel <= 0) {
        return;
      }
      const current = mapMetersPerPixel();
      if (!Number.isFinite(current) || current <= 0) {
        return;
      }
      window.clearTimeout(mapZoomSyncTimer);
      mapZoomSyncTimer = null;
      const level = Math.max(1, Math.min(14,
        map.getLevel() + Math.round(Math.log2(metersPerPixel / current))));
      if (level !== map.getLevel()) {
        expectedMapZoomLevel = level;
        map.setLevel(level, { animate: false });
      }
    }

    function scheduleMapZoomSync() {
      const map = getMap();
      if (expectedMapZoomLevel === map.getLevel()) {
        expectedMapZoomLevel = null;
        return;
      }
      expectedMapZoomLevel = null;
      window.clearTimeout(mapZoomSyncTimer);
      mapZoomSyncTimer = window.setTimeout(() => {
        mapZoomSyncTimer = null;
        const map = getMap(), qgisBridge = getBridge();
        if (!qgisBridge || typeof qgisBridge.zoomQgisView !== "function") {
          return;
        }
        const position = map.getCenter();
        const resolution = mapMetersPerPixel();
        if (Number.isFinite(resolution) && resolution > 0) {
          qgisBridge.zoomQgisView(position.getLng(), position.getLat(), resolution);
        }
      }, 150);
    }

    function configureMapWheel(container) {
      let accumulated = 0;
      let lastWheelAt = 0;
      // Register before SDK construction, so its native handler cannot also
      // zoom the same wheel event. Touch gestures still use the SDK normally.
      container.addEventListener("wheel", (event) => {
        if (event.ctrlKey || event.metaKey) {
          // Preserve browser zoom/pinch default, but keep the SDK wheel handler
          // from preventing it or zooming the map as well.
          accumulated = 0;
          event.stopImmediatePropagation();
          return;
        }
        const map = getMap(), kakao = { maps: getMaps() };
        if (!map || !Number.isFinite(event.deltaY) || event.deltaY === 0) {
          return;
        }
        event.preventDefault();
        event.stopImmediatePropagation();
        const now = Date.now();
        if (now - lastWheelAt > 200 || Math.sign(accumulated) !== Math.sign(event.deltaY)) {
          accumulated = 0;
        }
        lastWheelAt = now;
        const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? container.clientHeight : 1;
        accumulated += event.deltaY * unit;
        if (Math.abs(accumulated) < 40) {
          return;
        }
        const level = Math.max(1, Math.min(14, map.getLevel() + Math.sign(accumulated)));
        accumulated = 0;
        if (level === map.getLevel()) {
          return;
        }
        const rect = container.getBoundingClientRect();
        const anchor = map.getProjection().coordsFromContainerPoint(
          new kakao.maps.Point(event.clientX - rect.left, event.clientY - rect.top)
        );
        map.setLevel(level, { anchor, animate: false });
      }, { capture: true, passive: false });
    }

    function moveViewer(lon, lat, updateRoadview = true) {
      const map = getMap(), marker = getMarker(), kakao = { maps: getMaps() };
      const position = new kakao.maps.LatLng(lat, lon);
      map.setCenter(position);
      if (!updateRoadview) {
        // Keep the panorama marker at its actual position, not the zoom center.
        // Also reject a lookup that was still pending before this zoom.
        ++moveRequestId;
        return;
      }
      marker.setPosition(position);
      updateRoadviewPosition(position);
    }

    function updateRoadviewPosition(position) {
      const roadviewClient = getRoadviewClient(), roadview = getRoadview();
      const requestId = ++moveRequestId;
      const lon = position.getLng();
      const lat = position.getLat();
      roadviewClient.getNearestPanoId(position, 80, (panoId) => {
        if (requestId !== moveRequestId) {
          return;
        }

        if (panoId) {
          programmaticRoadviewPanoId = panoId;
          roadview.setPanoId(panoId, position);
          setStatus(`EPSG:4326 ${lat.toFixed(6)}, ${lon.toFixed(6)} · 로드뷰를 불러왔습니다.`);
        } else {
          setStatus(`EPSG:4326 ${lat.toFixed(6)}, ${lon.toFixed(6)} · 주변에 로드뷰 촬영 지점이 없습니다.`);
        }
      });
    }

    function onMapDragEnd() {
      window.clearTimeout(mapSyncTimer);
      mapSyncTimer = null;
      syncKakaoMapToQgis(true);
    }

    function onRoadviewPositionChanged() {
        const roadview = getRoadview(), map = getMap(), marker = getMarker();
        scheduleRoadviewStateSync();

        const panoId = roadview.getPanoId();
        if (programmaticRoadviewPanoId === panoId) {
          programmaticRoadviewPanoId = null;
          return;
        }
        programmaticRoadviewPanoId = null;

        const position = roadview.getPosition();
        if (!position) {
          return;
        }

        const lat = position.getLat();
        const lon = position.getLng();
        map.setCenter(position);
        marker.setPosition(position);

        window.clearTimeout(roadviewSyncTimer);
        roadviewSyncTimer = window.setTimeout(() => {
          const qgisBridge = getBridge();
          if (!qgisBridge) {
            setStatus("로드뷰 위치를 QGIS에 전달할 연결이 아직 준비되지 않았습니다.");
            return;
          }

          qgisBridge.moveQgisCenter(lon, lat);
          setStatus(`로드뷰 → QGIS EPSG:4326 ${lat.toFixed(6)}, ${lon.toFixed(6)}`);
        }, 200);
    }

    function reset() {
      for (const timer of [mapSyncTimer, roadviewSyncTimer, roadviewStateTimer, mapZoomSyncTimer]) {
        window.clearTimeout(timer);
      }
      mapSyncTimer = roadviewSyncTimer = roadviewStateTimer = mapZoomSyncTimer = null;
      expectedMapZoomLevel = programmaticRoadviewPanoId = null;
      ++moveRequestId;
    }

    return {
      syncKakaoMapToQgis, scheduleKakaoMapSync, syncRoadviewStateToQgis,
      scheduleRoadviewStateSync, mapMetersPerPixel, applyMapResolution,
      scheduleMapZoomSync, configureMapWheel, moveViewer, updateRoadviewPosition,
      onMapDragEnd, onRoadviewPositionChanged, reset
    };
};
