/* Session history list, selection and bridge actions. */
window.createKakaoHistoryController = function createKakaoHistoryController({
  document, routeHistoryList, getBridge, getActiveTab, setStatus,
  renderRouteGuidance, formatGuidanceDistance, formatGuidanceDuration,
  activateRoutePanelTab, updateRouteControls, updateRoutePanelVisibility,
  scheduleStableRelayout
}) {
    let routeHistory = [];
    let selectedRouteHistoryIds = new Set();
    let activeRouteHistoryId = "";

    function routePriorityLabel(priority) {
      const labels = {
        RECOMMEND: "추천",
        TIME: "최단 시간",
        DISTANCE: "최단 거리"
      };
      return labels[priority] || priority || "";
    }

    function formatHistoryTime(value) {
      if (!value) {
        return "";
      }
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) {
        return value;
      }
      const month = String(date.getMonth() + 1).padStart(2, "0");
      const day = String(date.getDate()).padStart(2, "0");
      const hour = String(date.getHours()).padStart(2, "0");
      const minute = String(date.getMinutes()).padStart(2, "0");
      return `${month}-${day} ${hour}:${minute}`;
    }

    function selectRouteHistory(history, item) {
      activeRouteHistoryId = history.history_id || "";
      routeHistoryList.querySelectorAll(".history-item").forEach((candidate) => {
        candidate.classList.toggle("is-active", candidate === item);
      });
      if (getBridge() && activeRouteHistoryId) {
        getBridge().selectRouteHistory(activeRouteHistoryId);
      }
      setStatus(`${history.origin_name || "출발지"} → ${history.destination_name || "도착지"}`);
    }

    function selectedRouteHistoriesFromCurrentList() {
      const availableIds = new Set(routeHistory.map((history) => history.history_id));
      selectedRouteHistoryIds = new Set(
        [...selectedRouteHistoryIds].filter((historyId) => availableIds.has(historyId))
      );
      return [...selectedRouteHistoryIds];
    }

    function createHistoryBulkActions() {
      const selectedIds = selectedRouteHistoriesFromCurrentList();
      const controls = document.createElement("div");
      controls.className = "history-bulk-actions";

      const summary = document.createElement("span");
      summary.className = "history-bulk-summary";
      summary.textContent = selectedIds.length
        ? `선택 ${selectedIds.length}건`
        : `경로 이력 ${routeHistory.length}건`;

      const loadHistoryButton = document.createElement("button");
      loadHistoryButton.type = "button";
      loadHistoryButton.textContent = "이력 불러오기";
      loadHistoryButton.addEventListener("click", () => {
        if (!getBridge() || typeof getBridge().loadRouteHistoryFile !== "function") {
          setStatus("경로 이력 불러오기 기능을 사용할 수 없습니다.");
          return;
        }
        getBridge().loadRouteHistoryFile();
      });

      const selectAllButton = document.createElement("button");
      selectAllButton.type = "button";
      selectAllButton.textContent = selectedIds.length === routeHistory.length && routeHistory.length
        ? "전체 해제"
        : "전체 선택";
      selectAllButton.disabled = !routeHistory.length;
      selectAllButton.addEventListener("click", () => {
        if (selectedRouteHistoryIds.size === routeHistory.length) {
          selectedRouteHistoryIds.clear();
        } else {
          selectedRouteHistoryIds = new Set(
            routeHistory.map((history) => history.history_id).filter(Boolean)
          );
        }
        renderRouteHistory({
          selected_history_id: activeRouteHistoryId,
          items: routeHistory
        });
      });

      const deleteAllButton = document.createElement("button");
      deleteAllButton.type = "button";
      deleteAllButton.textContent = "전체 삭제";
      deleteAllButton.disabled = !routeHistory.length;
      deleteAllButton.addEventListener("click", () => {
        if (!getBridge() || typeof getBridge().deleteAllRouteHistories !== "function") {
          setStatus("전체 이력 삭제 기능을 사용할 수 없습니다.");
          return;
        }
        getBridge().deleteAllRouteHistories();
      });

      const exportSelectedButton = document.createElement("button");
      exportSelectedButton.type = "button";
      exportSelectedButton.textContent = "선택 저장";
      exportSelectedButton.disabled = !selectedIds.length;
      exportSelectedButton.addEventListener("click", () => {
        const historyIds = selectedRouteHistoriesFromCurrentList();
        if (!historyIds.length) {
          setStatus("저장할 경로 이력을 선택하세요.");
          return;
        }
        if (!getBridge() || typeof getBridge().exportRouteHistories !== "function") {
          setStatus("선택 이력 저장 기능을 사용할 수 없습니다.");
          return;
        }
        getBridge().exportRouteHistories(JSON.stringify(historyIds));
      });

      controls.append(
        summary,
        loadHistoryButton,
        selectAllButton,
        deleteAllButton,
        exportSelectedButton
      );
      return controls;
    }

    function renderRouteHistory(payload) {
      payload = payload || {};
      const items = Array.isArray(payload.items) ? payload.items : [];
      const previousHistoryId = activeRouteHistoryId;
      routeHistory = items;
      const selectedHistoryId = payload.selected_history_id || activeRouteHistoryId || "";
      const selectedExists = items.some((history) => history.history_id === selectedHistoryId);
      activeRouteHistoryId = selectedExists ? selectedHistoryId : "";
      routeHistoryList.textContent = "";

      if (previousHistoryId && !activeRouteHistoryId) {
        renderRouteGuidance({ history_id: "", summary: {}, path: [], guides: [] });
      }

      routeHistoryList.appendChild(createHistoryBulkActions());

      if (!items.length) {
        const empty = document.createElement("div");
        empty.className = "history-empty";
        empty.textContent = "아직 경로 이력이 없습니다.";
        routeHistoryList.appendChild(empty);
      }

      items.forEach((history) => {
        const item = document.createElement("div");
        item.className = "history-item";
        item.setAttribute("role", "option");
        item.setAttribute("tabindex", "0");
        if (history.history_id === activeRouteHistoryId) {
          item.classList.add("is-active");
        }

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.className = "history-select";
        checkbox.title = "저장할 이력 선택";
        checkbox.setAttribute("aria-label", "저장할 이력 선택");
        checkbox.checked = selectedRouteHistoryIds.has(history.history_id);
        checkbox.addEventListener("click", (event) => {
          event.stopPropagation();
        });
        checkbox.addEventListener("change", () => {
          if (checkbox.checked) {
            selectedRouteHistoryIds.add(history.history_id);
          } else {
            selectedRouteHistoryIds.delete(history.history_id);
          }
          renderRouteHistory({
            selected_history_id: activeRouteHistoryId,
            items: routeHistory
          });
        });

        const content = document.createElement("span");
        content.className = "history-content";

        const title = document.createElement("span");
        title.className = "history-title";
        title.textContent = `${history.origin_name || "출발지"} → ${history.destination_name || "도착지"}`;

        const summary = document.createElement("span");
        summary.className = "history-meta";
        summary.textContent = history.result_summary || [
          formatGuidanceDuration(Number(history.duration_s)),
          formatGuidanceDistance(Number(history.distance_m)),
          `안내 ${Number(history.guidance_count) || 0}개`
        ].filter(Boolean).join(" · ");

        const options = document.createElement("span");
        options.className = "history-meta";
        const optionParts = [
          routePriorityLabel(history.priority),
          history.avoid ? `회피 ${history.avoid.split("|").filter(Boolean).length}` : "",
          formatHistoryTime(history.searched_at)
        ].filter(Boolean);
        options.textContent = optionParts.join(" · ");

        const actions = document.createElement("span");
        actions.className = "history-actions";
        [
          ["불러오기", "loadRouteHistory"],
          ["삭제", "deleteRouteHistory"],
          ["내보내기", "exportRouteHistory"]
        ].forEach(([label, bridgeMethod]) => {
          const button = document.createElement("button");
          button.type = "button";
          button.textContent = label;
          button.addEventListener("click", (event) => {
            event.stopPropagation();
            if (getBridge() && history.history_id) {
              getBridge()[bridgeMethod](history.history_id);
            }
          });
          actions.appendChild(button);
        });

        content.append(title, summary, options, actions);
        item.append(checkbox, content);
        item.addEventListener("click", () => selectRouteHistory(history, item));
        item.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            selectRouteHistory(history, item);
          }
        });
        routeHistoryList.appendChild(item);
      });

      if (getActiveTab() === "history") {
        activateRoutePanelTab("history");
      }
      updateRouteControls();
      updateRoutePanelVisibility();
      scheduleStableRelayout();
    }

    return {
      render: renderRouteHistory,
      get count() { return routeHistory.length; },
      get activeId() { return activeRouteHistoryId; },
      selectedIds: selectedRouteHistoriesFromCurrentList
    };
};
