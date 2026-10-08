/* Guidance list, overview and SDK route overlay. */
window.createKakaoGuidanceController = function createKakaoGuidanceController({
  document, routeGuidanceList, routeGuidanceSummaryText, routeGuidanceOverview,
  routeGuidancePanel, routeGuidanceToggle, getMap, getMaps, getBridge, getActiveTab,
  moveViewer, setStatus, formatCoordinate, activateRoutePanelTab,
  updateRoutePanelVisibility, scheduleStableRelayout
}) {
    let routeGuidance = [];
    let latestRouteGuidancePayload = null;
    let routePolyline = null;
    let activeGuidanceSequence = null;

    function formatGuidanceDistance(distance) {
      if (!Number.isFinite(distance) || distance <= 0) {
        return "";
      }
      if (distance < 1000) {
        return `${Math.round(distance)} m`;
      }
      return `${(distance / 1000).toFixed(1)} km`;
    }

    function formatGuidanceDuration(duration) {
      if (!Number.isFinite(duration) || duration <= 0) {
        return "";
      }
      if (duration < 60) {
        return `${Math.round(duration)}초`;
      }
      return `${Math.max(1, Math.round(duration / 60))}분`;
    }

    function guidanceIconText(category) {
      const icons = {
        start: "출",
        destination: "도",
        waypoint: "경",
        straight: "↑",
        left: "↰",
        right: "↱",
        uturn: "↶",
        roundabout: "⟳",
        transition: "↗",
        other: "•"
      };
      return icons[category] || icons.other;
    }

    function selectRouteGuidance(guide, item) {
      activeGuidanceSequence = guide.sequence;
      routeGuidanceList.querySelectorAll(".guidance-item").forEach((candidate) => {
        candidate.classList.toggle("is-active", candidate === item);
      });

      const qgisBridge = getBridge();
      moveViewer(guide.longitude, guide.latitude);
      if (qgisBridge) {
        qgisBridge.selectRouteGuidance(
          guide.sequence,
          guide.longitude,
          guide.latitude
        );
      }
      setStatus(`${guide.sequence}. ${guide.guidance}`);
    }

    function clearRoutePath() {
      if (routePolyline) {
        routePolyline.setMap(null);
        routePolyline = null;
      }
    }

    function renderRoutePath(path) {
      clearRoutePath();
      const map = getMap();
      if (!map || !Array.isArray(path) || path.length < 2) {
        return;
      }

      const linePath = path
        .map((point) => ({
          lat: Number(point.lat),
          lon: Number(point.lon)
        }))
        .filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lon))
        .map((point) => new (getMaps().LatLng)(point.lat, point.lon));

      if (linePath.length < 2) {
        return;
      }

      routePolyline = new (getMaps().Polyline)({
        map,
        path: linePath,
        strokeWeight: 5,
        strokeColor: "#1976d2",
        strokeOpacity: 0.9,
        strokeStyle: "solid"
      });

      const bounds = new (getMaps().LatLngBounds)();
      linePath.forEach((point) => bounds.extend(point));
      map.setBounds(bounds);
      scheduleStableRelayout();
    }

    function renderRouteGuidance(payload) {
      const routePayload = payload || {};
      latestRouteGuidancePayload = routePayload;
      const guides = Array.isArray(routePayload.guides) ? routePayload.guides : [];
      routeGuidance = guides;
      activeGuidanceSequence = null;
      routeGuidanceList.textContent = "";
      renderRouteOverview(routePayload);
      renderRoutePath(routePayload.path);

      if (!guides.length) {
        routeGuidanceSummaryText.dataset.guidanceSummary = "";
        routeGuidanceOverview.textContent = "";
        routeGuidanceOverview.hidden = true;
        updateRoutePanelVisibility();
        scheduleStableRelayout();
        return;
      }

      const summary = routePayload.summary || {};
      const vehicle = summary.vehicle || {};
      const vehicleTypeLabels = {
        1: "소형",
        2: "중형",
        3: "대형",
        4: "대형 화물",
        5: "특수 화물",
        6: "경차",
        7: "이륜차"
      };
      const summaryParts = [
        formatGuidanceDuration(Number(summary.duration_s)),
        formatGuidanceDistance(Number(summary.distance_m)),
        Array.isArray(summary.avoid) && summary.avoid.length
          ? `회피 ${summary.avoid.length}`
          : "",
        vehicleTypeLabels[vehicle.car_type] || "",
        `안내 ${guides.length}개`
      ].filter(Boolean);
      routeGuidanceSummaryText.dataset.guidanceSummary = summaryParts.join(" · ");
      routeGuidancePanel.dataset.collapsed = "false";
      routeGuidanceToggle.textContent = "−";
      routeGuidanceToggle.title = "경로 안내 접기";
      routeGuidanceToggle.setAttribute("aria-label", "경로 안내 접기");

      guides.forEach((guide) => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "guidance-item";
        item.setAttribute("role", "option");

        const sequence = document.createElement("span");
        sequence.className = "guidance-sequence";
        sequence.textContent = String(guide.sequence);

        const icon = document.createElement("span");
        icon.className = `guidance-icon ${guide.category || "other"}`;
        icon.textContent = guidanceIconText(guide.category);
        icon.setAttribute("aria-hidden", "true");

        const copy = document.createElement("span");
        copy.className = "guidance-copy";

        const title = document.createElement("span");
        title.className = "guidance-title";
        title.textContent = guide.guidance || guide.name || "경로 안내";

        const meta = document.createElement("span");
        meta.className = "guidance-meta";
        const metaParts = [
          formatGuidanceDistance(Number(guide.distance_m)),
          formatGuidanceDuration(Number(guide.duration_s))
        ].filter(Boolean);
        meta.textContent = metaParts.length ? metaParts.join(" · ") : "현재 위치";

        copy.append(title, meta);
        item.append(sequence, icon, copy);
        item.addEventListener("click", () => selectRouteGuidance(guide, item));
        routeGuidanceList.appendChild(item);
      });

      activateRoutePanelTab("guidance");
      updateRoutePanelVisibility();
      scheduleStableRelayout();
    }

    function routeInputLabel(location, fallback) {
      const label = location && location.label ? String(location.label).trim() : "";
      if (label) {
        return label;
      }
      if (
        location &&
        Number.isFinite(Number(location.lon)) &&
        Number.isFinite(Number(location.lat))
      ) {
        return formatCoordinate({
          lon: Number(location.lon),
          lat: Number(location.lat)
        });
      }
      return fallback;
    }

    function routePointTooltip(location) {
      if (
        location &&
        Number.isFinite(Number(location.lon)) &&
        Number.isFinite(Number(location.lat))
      ) {
        return `${Number(location.lon).toFixed(7)}, ${Number(location.lat).toFixed(7)}`;
      }
      return "";
    }

    function renderRouteOverview(payload) {
      const points = [];
      if (payload && payload.origin) {
        points.push({
          role: "출발",
          location: payload.origin,
          fallback: "출발지"
        });
      }

      const waypoints = payload && Array.isArray(payload.waypoints)
        ? payload.waypoints
        : [];
      waypoints.forEach((waypoint, index) => {
        points.push({
          role: `경유 ${index + 1}`,
          location: waypoint,
          fallback: `경유지 ${index + 1}`
        });
      });

      if (payload && payload.destination) {
        points.push({
          role: "도착",
          location: payload.destination,
          fallback: "도착지"
        });
      }

      routeGuidanceOverview.textContent = "";
      if (!points.length) {
        routeGuidanceOverview.hidden = true;
        return;
      }

      points.forEach((point) => {
        const item = document.createElement("span");
        item.className = "route-overview-point";
        const tooltip = routePointTooltip(point.location);
        if (tooltip) {
          item.title = tooltip;
        }

        const role = document.createElement("span");
        role.className = "route-overview-role";
        role.textContent = point.role;

        const label = document.createElement("span");
        label.className = "route-overview-label";
        label.textContent = routeInputLabel(point.location, point.fallback);

        item.append(role, label);
        routeGuidanceOverview.appendChild(item);
      });
      routeGuidanceOverview.hidden = getActiveTab() === "history";
    }

    return {
      render: renderRouteGuidance,
      clearPath: clearRoutePath,
      inputLabel: routeInputLabel,
      formatDistance: formatGuidanceDistance,
      formatDuration: formatGuidanceDuration,
      get count() { return routeGuidance.length; },
      get payload() { return latestRouteGuidancePayload; },
      get activeSequence() { return activeGuidanceSequence; }
    };
};
