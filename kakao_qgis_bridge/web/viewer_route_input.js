/* Route input editing, waypoint order, location resolution and requests. */
window.createKakaoRouteInputController = function createKakaoRouteInputController({
  document, ui, maxRouteWaypoints, getMap, getBridge, getServices,
  search, cancelSearch, timers, moveViewer, setStatus, formatCoordinate,
  routeInputLabel, clearRoutePath
}) {
    const { routeOriginInput, routeDestinationInput, routeOriginCurrentButton, routeDestinationCurrentButton, routePrioritySelect, routeAvoidToggle, routeAvoidOptions, routeAvoidCheckboxes, routeVehicleToggle, routeVehicleOptions, routeCarType, routeCarFuel, routeCarHipass, routeAddWaypointButton, routeWaypointsContainer, routeCreateButton, routeHistoryOpenButton, routeSwapButton, routeResetButton, searchResults } = ui;
    let routeOrigin = null;
    let routeDestination = null;
    const routeWaypoints = [];
    let nextWaypointId = 1;
    let routeBusy = false;
    let routeSearchTimer = null;
    let requestGeneration = 0;

    function selectedRouteAvoidOptions() {
      return routeAvoidCheckboxes
        .filter((checkbox) => checkbox.checked)
        .map((checkbox) => checkbox.value);
    }

    function updateRouteAvoidSummary() {
      const selected = routeAvoidCheckboxes.filter((checkbox) => checkbox.checked);
      routeAvoidToggle.textContent = `회피 ${selected.length}`;
      const labels = selected.map((checkbox) => checkbox.parentElement.textContent.trim());
      routeAvoidToggle.title = labels.length
        ? `경로 회피: ${labels.join(", ")}`
        : "경로 회피 옵션";
    }

    function selectedRouteVehicleOptions() {
      return {
        car_type: Number(routeCarType.value),
        car_fuel: routeCarFuel.value,
        car_hipass: routeCarHipass.checked
      };
    }

    function updateRouteVehicleSummary() {
      const typeLabel = routeCarType.options[routeCarType.selectedIndex].text;
      const fuelLabel = routeCarFuel.options[routeCarFuel.selectedIndex].text;
      const hipassLabel = routeCarHipass.checked ? ", 하이패스" : "";
      routeVehicleToggle.title = `차량: ${typeLabel}, ${fuelLabel}${hipassLabel}`;
    }

    function currentMapCoordinate() {
      const map = getMap();
      if (!map) {
        return null;
      }
      const center = map.getCenter();
      return {
        lon: center.getLng(),
        lat: center.getLat()
      };
    }

    function parseCoordinateInput(value) {
      const separator = value.includes(",") ? /\s*,\s*/ : /\s+/;
      const parts = value.trim().split(separator);
      if (parts.length !== 2 || parts.some((part) => !part)) {
        return null;
      }

      const first = Number(parts[0]);
      const second = Number(parts[1]);
      if (!Number.isFinite(first) || !Number.isFinite(second)) {
        return null;
      }

      let lon = first;
      let lat = second;
      if (Math.abs(second) > 90 && Math.abs(first) <= 90) {
        lon = second;
        lat = first;
      }

      if (Math.abs(lon) > 180 || Math.abs(lat) > 90) {
        return null;
      }
      return { lon, lat };
    }

    function resolveRouteLocation(value) {
      const { placesService, geocoderService, status: searchStatus } = getServices();
      const query = value.trim();
      const coordinate = parseCoordinateInput(query);
      if (coordinate) {
        return Promise.resolve(coordinate);
      }
      if (!query || !placesService || !geocoderService) {
        return Promise.reject(new Error("입력값을 좌표나 장소로 해석할 수 없습니다."));
      }

      return new Promise((resolve, reject) => {
        const addressResults = [];
        const placeResults = [];
        let remaining = 2;

        const finish = () => {
          remaining -= 1;
          if (remaining > 0) {
            return;
          }

          const result = [...addressResults, ...placeResults].find((point) => (
            Number.isFinite(point.lon) && Number.isFinite(point.lat) &&
            Math.abs(point.lon) <= 180 && Math.abs(point.lat) <= 90
          ));
          if (!result) {
            reject(new Error(`위치를 찾지 못했습니다: ${query}`));
            return;
          }
          resolve(result);
        };

        geocoderService.addressSearch(query, (data, status) => {
          if (status === searchStatus.OK) {
            data.forEach((item) => {
              addressResults.push({ lon: Number(item.x), lat: Number(item.y) });
            });
          }
          finish();
        });

        placesService.keywordSearch(query, (data, status) => {
          if (status === searchStatus.OK) {
            data.forEach((item) => {
              placeResults.push({ lon: Number(item.x), lat: Number(item.y) });
            });
          }
          finish();
        });
      });
    }

    function updateRouteControls() {
      const map = getMap();
      const hasOrigin = Boolean(routeOriginInput.value.trim());
      const hasDestination = Boolean(routeDestinationInput.value.trim());
      const waypointsReady = routeWaypoints.every((waypoint) => waypoint.input.value.trim());
      routeCreateButton.disabled = routeBusy || !(hasOrigin && hasDestination && waypointsReady);
      routeHistoryOpenButton.disabled = routeBusy || !getBridge();
      routeResetButton.disabled = routeBusy || !(hasOrigin || hasDestination || routeWaypoints.length);
      routeSwapButton.disabled = !map || routeBusy || !(hasOrigin || hasDestination);
      routePrioritySelect.disabled = !map || routeBusy;
      routeAvoidToggle.disabled = !map || routeBusy;
      routeAvoidCheckboxes.forEach((checkbox) => {
        checkbox.disabled = !map || routeBusy;
      });
      routeVehicleToggle.disabled = !map || routeBusy;
      routeCarType.disabled = !map || routeBusy;
      routeCarFuel.disabled = !map || routeBusy;
      routeCarHipass.disabled = !map || routeBusy;
      routeAddWaypointButton.disabled = !map || routeBusy || routeWaypoints.length >= maxRouteWaypoints;
      routeOriginInput.disabled = !map || routeBusy;
      routeDestinationInput.disabled = !map || routeBusy;
      routeOriginCurrentButton.disabled = !map || routeBusy;
      routeDestinationCurrentButton.disabled = !map || routeBusy;
      routeWaypoints.forEach((waypoint, index) => {
        waypoint.input.disabled = !map || routeBusy;
        waypoint.currentButton.disabled = !map || routeBusy;
        waypoint.removeButton.disabled = routeBusy;
        waypoint.upButton.disabled = routeBusy || index === 0;
        waypoint.downButton.disabled = routeBusy || index === routeWaypoints.length - 1;
      });
    }

    function publishRoutePoint(role, coordinate) {
      if (getBridge() && coordinate) {
        getBridge().setRoutePoint(role, coordinate.lon, coordinate.lat);
      }
    }

    function applyRouteSearchResult(
      input,
      pointId,
      label,
      coordinate,
      displayValue,
      onResolved
    ) {
      const map = getMap();
      input.value = displayValue || formatCoordinate(coordinate);
      onResolved(coordinate);
      publishRoutePoint(pointId, coordinate);
      searchResults.hidden = true;

      if (map) {
        map.setLevel(4);
        moveViewer(coordinate.lon, coordinate.lat);
      }
      if (getBridge()) {
        getBridge().moveQgisCenter(coordinate.lon, coordinate.lat);
      }
      setStatus(
        `${label} 지정: ${coordinate.lat.toFixed(6)}, ${coordinate.lon.toFixed(6)}`
      );
      updateRouteControls();
    }

    function searchRouteInput(
      input,
      pointIdProvider,
      labelProvider,
      onResolved,
      selectFirst = false
    ) {
      const query = input.value.trim();
      if (!query) {
        return;
      }

      const pointId = pointIdProvider();
      const label = labelProvider();
      const coordinate = parseCoordinateInput(query);
      if (coordinate) {
        applyRouteSearchResult(
          input,
          pointId,
          label,
          coordinate,
          formatCoordinate(coordinate),
          onResolved
        );
        return;
      }

      search(
        query,
        (result) => {
          applyRouteSearchResult(
            input,
            pointId,
            label,
            { lon: result.lon, lat: result.lat },
            result.title || result.address,
            onResolved
          );
        },
        false,
        selectFirst
      );
    }

    function bindRouteInput(input, pointIdProvider, labelProvider, onResolved) {
      input.addEventListener("input", () => {
        onResolved(null);
        cancelSearch();
        searchResults.hidden = true;
        if (getBridge()) {
          getBridge().clearRoutePoint(pointIdProvider());
        }
        updateRouteControls();

        timers.clearTimeout(routeSearchTimer);
        if (!input.value.trim()) {
          return;
        }
        routeSearchTimer = timers.setTimeout(() => {
          searchRouteInput(input, pointIdProvider, labelProvider, onResolved);
        }, 500);
      });

      input.addEventListener("keydown", (event) => {
        if (event.key !== "Enter") {
          return;
        }
        event.preventDefault();
        timers.clearTimeout(routeSearchTimer);
        searchRouteInput(
          input,
          pointIdProvider,
          labelProvider,
          onResolved,
          true
        );
      });
    }

    function waypointPointId(waypoint) {
      return `waypoint:${waypoint.id}`;
    }

    function updateWaypointLabels() {
      routeWaypoints.forEach((waypoint, index) => {
        waypoint.label.textContent = `경유 ${index + 1}`;
        waypoint.input.setAttribute("aria-label", `경유지 ${index + 1}`);
        waypoint.currentButton.title = `현재 지도 중심을 경유지 ${index + 1}로 사용`;
        waypoint.removeButton.title = `경유지 ${index + 1} 삭제`;
        waypoint.removeButton.setAttribute("aria-label", `경유지 ${index + 1} 삭제`);
        waypoint.upButton.title = `경유지 ${index + 1} 위로 이동`;
        waypoint.upButton.setAttribute("aria-label", `경유지 ${index + 1} 위로 이동`);
        waypoint.downButton.title = `경유지 ${index + 1} 아래로 이동`;
        waypoint.downButton.setAttribute("aria-label", `경유지 ${index + 1} 아래로 이동`);
      });
    }

    function moveWaypoint(waypoint, offset) {
      const index = routeWaypoints.indexOf(waypoint);
      const targetIndex = index + offset;
      if (index < 0 || targetIndex < 0 || targetIndex >= routeWaypoints.length) {
        return;
      }

      timers.clearTimeout(routeSearchTimer);
      cancelSearch();
      searchResults.hidden = true;
      routeWaypoints.splice(index, 1);
      routeWaypoints.splice(targetIndex, 0, waypoint);
      routeWaypointsContainer.replaceChildren(
        ...routeWaypoints.map((candidate) => candidate.row)
      );
      updateWaypointLabels();
      updateRouteControls();
      setStatus(`경유지 ${targetIndex + 1} 순서로 이동했습니다.`);
    }

    function swapRouteEndpoints() {
      timers.clearTimeout(routeSearchTimer);
      cancelSearch();
      searchResults.hidden = true;

      const originValue = routeOriginInput.value;
      routeOriginInput.value = routeDestinationInput.value;
      routeDestinationInput.value = originValue;
      [routeOrigin, routeDestination] = [routeDestination, routeOrigin];

      if (getBridge()) {
        getBridge().clearRoutePoint("origin");
        getBridge().clearRoutePoint("destination");
        publishRoutePoint("origin", routeOrigin);
        publishRoutePoint("destination", routeDestination);
      }
      updateRouteControls();
      setStatus("출발지와 도착지를 바꿨습니다.");
    }

    function removeWaypoint(waypoint) {
      const index = routeWaypoints.indexOf(waypoint);
      if (index < 0) {
        return;
      }
      timers.clearTimeout(routeSearchTimer);
      cancelSearch();
      searchResults.hidden = true;
      if (getBridge()) {
        getBridge().clearRoutePoint(waypointPointId(waypoint));
      }
      routeWaypoints.splice(index, 1);
      waypoint.row.remove();
      updateWaypointLabels();
      updateRouteControls();
      setStatus("경유지를 삭제했습니다.");
    }

    function addWaypoint() {
      if (routeWaypoints.length >= maxRouteWaypoints) {
        setStatus(`경유지는 최대 ${maxRouteWaypoints}개까지 추가할 수 있습니다.`);
        return;
      }

      const row = document.createElement("div");
      row.className = "route-waypoint";

      const label = document.createElement("span");
      label.className = "route-label";

      const input = document.createElement("input");
      input.className = "route-input";
      input.type = "text";
      input.placeholder = "주소·장소 또는 경도,위도";
      input.autocomplete = "off";

      const currentButton = document.createElement("button");
      currentButton.className = "route-current";
      currentButton.type = "button";
      currentButton.textContent = "현재 위치";

      const removeButton = document.createElement("button");
      removeButton.className = "route-waypoint-remove";
      removeButton.type = "button";
      removeButton.textContent = "×";

      const orderContainer = document.createElement("span");
      orderContainer.className = "route-waypoint-order";

      const upButton = document.createElement("button");
      upButton.type = "button";
      upButton.textContent = "↑";

      const downButton = document.createElement("button");
      downButton.type = "button";
      downButton.textContent = "↓";

      const waypoint = {
        id: nextWaypointId++,
        coordinate: null,
        row,
        label,
        input,
        currentButton,
        removeButton,
        upButton,
        downButton
      };

      bindRouteInput(
        input,
        () => waypointPointId(waypoint),
        () => `경유지 ${routeWaypoints.indexOf(waypoint) + 1}`,
        (coordinate) => {
          waypoint.coordinate = coordinate;
        }
      );

      currentButton.addEventListener("click", () => {
        timers.clearTimeout(routeSearchTimer);
        cancelSearch();
        searchResults.hidden = true;
        waypoint.coordinate = currentMapCoordinate();
        if (waypoint.coordinate) {
          input.value = formatCoordinate(waypoint.coordinate);
          publishRoutePoint(waypointPointId(waypoint), waypoint.coordinate);
          const index = routeWaypoints.indexOf(waypoint) + 1;
          setStatus(
            `경유지 ${index}: ${waypoint.coordinate.lat.toFixed(6)}, ` +
            waypoint.coordinate.lon.toFixed(6)
          );
        }
        updateRouteControls();
      });

      removeButton.addEventListener("click", () => removeWaypoint(waypoint));
      upButton.addEventListener("click", () => moveWaypoint(waypoint, -1));
      downButton.addEventListener("click", () => moveWaypoint(waypoint, 1));
      orderContainer.append(upButton, downButton);

      row.append(label, input, currentButton, orderContainer, removeButton);
      routeWaypoints.push(waypoint);
      routeWaypointsContainer.appendChild(row);
      updateWaypointLabels();
      updateRouteControls();
      input.focus();
      setStatus(`${routeWaypoints.length}번째 경유지를 추가했습니다.`);
    }

    function clearRouteInputs(resetOptions = true, notifyQgis = true) {
      requestGeneration += 1;
      routeBusy = false;
      timers.clearTimeout(routeSearchTimer);
      cancelSearch();
      searchResults.hidden = true;
      routeOrigin = null;
      routeDestination = null;
      routeOriginInput.value = "";
      routeDestinationInput.value = "";
      routeWaypoints.forEach((waypoint) => waypoint.row.remove());
      routeWaypoints.length = 0;
      nextWaypointId = 1;

      if (resetOptions) {
        routePrioritySelect.value = "RECOMMEND";
        routeAvoidCheckboxes.forEach((checkbox) => {
          checkbox.checked = false;
        });
        routeCarType.value = "1";
        routeCarFuel.value = "GASOLINE";
        routeCarHipass.checked = false;
      }

      routeAvoidOptions.hidden = true;
      routeAvoidToggle.setAttribute("aria-expanded", "false");
      updateRouteAvoidSummary();
      routeVehicleOptions.hidden = true;
      routeVehicleToggle.setAttribute("aria-expanded", "false");
      updateRouteVehicleSummary();
      if (getBridge() && notifyQgis) {
        getBridge().clearRoutePoints();
      }
      updateRouteControls();
    }

    function applyLoadedRoutePoint(pointId, location) {
      const coordinate = {
        lon: Number(location.lon),
        lat: Number(location.lat)
      };
      if (!Number.isFinite(coordinate.lon) || !Number.isFinite(coordinate.lat)) {
        return null;
      }
      publishRoutePoint(pointId, coordinate);
      return coordinate;
    }

    function loadRouteHistoryInput(payload) {
      clearRouteInputs(false);

      const origin = payload.origin || {};
      const destination = payload.destination || {};
      routeOriginInput.value = routeInputLabel(origin, "출발지");
      routeDestinationInput.value = routeInputLabel(destination, "도착지");
      routeOrigin = applyLoadedRoutePoint("origin", origin);
      routeDestination = applyLoadedRoutePoint("destination", destination);

      const waypoints = Array.isArray(payload.waypoints)
        ? payload.waypoints.slice(0, maxRouteWaypoints)
        : [];
      waypoints.forEach((waypointPayload) => {
        addWaypoint();
        const waypoint = routeWaypoints[routeWaypoints.length - 1];
        waypoint.input.value = routeInputLabel(
          waypointPayload,
          `경유지 ${routeWaypoints.length}`
        );
        waypoint.coordinate = applyLoadedRoutePoint(
          waypointPointId(waypoint),
          waypointPayload
        );
      });

      if (payload.priority && routePrioritySelect.querySelector(`option[value="${payload.priority}"]`)) {
        routePrioritySelect.value = payload.priority;
      }

      const avoid = Array.isArray(payload.avoid) ? payload.avoid : [];
      routeAvoidCheckboxes.forEach((checkbox) => {
        checkbox.checked = avoid.includes(checkbox.value);
      });
      updateRouteAvoidSummary();

      const vehicle = payload.vehicle || {};
      if (vehicle.car_type !== undefined) {
        routeCarType.value = String(vehicle.car_type);
      }
      if (vehicle.car_fuel) {
        routeCarFuel.value = vehicle.car_fuel;
      }
      routeCarHipass.checked = Boolean(vehicle.car_hipass);
      updateRouteVehicleSummary();

      updateRouteControls();
      if (routeOrigin) {
        moveViewer(routeOrigin.lon, routeOrigin.lat);
      }
      setStatus("선택한 이력을 경로 입력창으로 불러왔습니다.");
    }

    routeAddWaypointButton.addEventListener("click", addWaypoint);

    routePrioritySelect.addEventListener("change", () => {
      const label = routePrioritySelect.options[routePrioritySelect.selectedIndex].text;
      setStatus(`경로 유형: ${label}`);
    });

    routeAvoidToggle.addEventListener("click", () => {
      const opening = routeAvoidOptions.hidden;
      routeAvoidOptions.hidden = !opening;
      routeAvoidToggle.setAttribute("aria-expanded", opening ? "true" : "false");
      if (opening) {
        routeVehicleOptions.hidden = true;
        routeVehicleToggle.setAttribute("aria-expanded", "false");
      }
    });

    routeAvoidCheckboxes.forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        updateRouteAvoidSummary();
        const count = selectedRouteAvoidOptions().length;
        setStatus(count ? `경로 회피 옵션 ${count}개 선택` : "경로 회피 옵션 없음");
      });
    });

    routeVehicleToggle.addEventListener("click", () => {
      const opening = routeVehicleOptions.hidden;
      routeVehicleOptions.hidden = !opening;
      routeVehicleToggle.setAttribute("aria-expanded", opening ? "true" : "false");
      if (opening) {
        routeAvoidOptions.hidden = true;
        routeAvoidToggle.setAttribute("aria-expanded", "false");
      }
    });

    [routeCarType, routeCarFuel, routeCarHipass].forEach((control) => {
      control.addEventListener("change", () => {
        updateRouteVehicleSummary();
        setStatus(routeVehicleToggle.title);
      });
    });

    routeSwapButton.addEventListener("click", swapRouteEndpoints);

    bindRouteInput(
      routeOriginInput,
      () => "origin",
      () => "출발지",
      (coordinate) => {
        routeOrigin = coordinate;
      }
    );

    bindRouteInput(
      routeDestinationInput,
      () => "destination",
      () => "도착지",
      (coordinate) => {
        routeDestination = coordinate;
      }
    );

    routeOriginCurrentButton.addEventListener("click", () => {
      timers.clearTimeout(routeSearchTimer);
      cancelSearch();
      searchResults.hidden = true;
      routeOrigin = currentMapCoordinate();
      if (routeOrigin) {
        routeOriginInput.value = formatCoordinate(routeOrigin);
        publishRoutePoint("origin", routeOrigin);
        setStatus(`출발지: ${routeOrigin.lat.toFixed(6)}, ${routeOrigin.lon.toFixed(6)}`);
      }
      updateRouteControls();
    });

    routeDestinationCurrentButton.addEventListener("click", () => {
      timers.clearTimeout(routeSearchTimer);
      cancelSearch();
      searchResults.hidden = true;
      routeDestination = currentMapCoordinate();
      if (routeDestination) {
        routeDestinationInput.value = formatCoordinate(routeDestination);
        publishRoutePoint("destination", routeDestination);
        setStatus(`도착지: ${routeDestination.lat.toFixed(6)}, ${routeDestination.lon.toFixed(6)}`);
      }
      updateRouteControls();
    });

    async function requestRoute() {
      if (routeBusy) return;
      const generation = ++requestGeneration;
      if (!getBridge()) {
        setStatus("QGIS 경로 탐색 연결이 아직 준비되지 않았습니다.");
        return;
      }

      timers.clearTimeout(routeSearchTimer);
      cancelSearch();
      searchResults.hidden = true;
      routeAvoidOptions.hidden = true;
      routeAvoidToggle.setAttribute("aria-expanded", "false");
      routeVehicleOptions.hidden = true;
      routeVehicleToggle.setAttribute("aria-expanded", "false");
      routeBusy = true;
      updateRouteControls();
      setStatus("출발지, 경유지, 도착지를 확인하고 있습니다...");

      try {
        const locations = await Promise.all([
          routeOrigin || resolveRouteLocation(routeOriginInput.value),
          ...routeWaypoints.map((waypoint) => (
            waypoint.coordinate || resolveRouteLocation(waypoint.input.value)
          )),
          routeDestination || resolveRouteLocation(routeDestinationInput.value)
        ]);
        if (generation !== requestGeneration) return;
        routeOrigin = locations[0];
        routeDestination = locations[locations.length - 1];
        routeWaypoints.forEach((waypoint, index) => {
          waypoint.coordinate = locations[index + 1];
        });
      } catch (error) {
        if (generation !== requestGeneration) return;
        routeBusy = false;
        setStatus(error.message);
        updateRouteControls();
        return;
      }

      if (generation !== requestGeneration) return;
      publishRoutePoint("origin", routeOrigin);
      publishRoutePoint("destination", routeDestination);
      routeWaypoints.forEach((waypoint) => {
        publishRoutePoint(waypointPointId(waypoint), waypoint.coordinate);
      });
      const waypointPayload = routeWaypoints.map((waypoint) => ({
        id: waypointPointId(waypoint),
        label: waypoint.input.value.trim(),
        lon: waypoint.coordinate.lon,
        lat: waypoint.coordinate.lat
      }));
      setStatus(
        routeWaypoints.length
          ? `경유지 ${routeWaypoints.length}개를 포함한 경로를 탐색하고 있습니다...`
          : "Kakao Mobility 경로를 탐색하고 있습니다..."
      );
      try {
        getBridge().requestRoute(
        routeOrigin.lon,
        routeOrigin.lat,
        routeDestination.lon,
        routeDestination.lat,
        routePrioritySelect.value,
        JSON.stringify(waypointPayload),
        JSON.stringify(selectedRouteAvoidOptions()),
        JSON.stringify(selectedRouteVehicleOptions()),
        routeOriginInput.value.trim(),
        routeDestinationInput.value.trim()
        );
      } catch (error) {
        if (generation !== requestGeneration) return;
        routeBusy = false;
        updateRouteControls();
        setStatus(error.message);
      }
    }
    routeCreateButton.addEventListener("click", requestRoute);

    routeResetButton.addEventListener("click", () => {
      clearRouteInputs(true);
      clearRoutePath();
      setStatus("경로 지점을 초기화했습니다.");
    });


    updateRouteVehicleSummary();
    return {
      updateControls: updateRouteControls,
      clear: clearRouteInputs,
      load: loadRouteHistoryInput,
      request: requestRoute,
      addWaypoint,
      complete() { routeBusy = false; updateRouteControls(); },
      reset() { clearRouteInputs(true, false); },
      get busy() { return routeBusy; },
      get waypointCount() { return routeWaypoints.length; },
      parseCoordinate: parseCoordinateInput
    };
};
