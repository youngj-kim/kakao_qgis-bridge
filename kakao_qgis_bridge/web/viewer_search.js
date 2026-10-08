/* Local place/address search; dependencies supplied by the viewer. */
window.createKakaoSearchController = function createKakaoSearchController({
  document, searchForm, searchQuery, searchSubmit, searchClear, searchResults,
  getServices, setStatus, selectSearchResult
}) {
    let searchRequestId = 0;

    function normalizePlaceResult(place) {
      return {
        title: place.place_name || place.address_name || "검색 결과",
        address: place.road_address_name || place.address_name || "",
        lon: Number(place.x),
        lat: Number(place.y)
      };
    }

    function normalizeAddressResult(address) {
      const detail = address.road_address && address.road_address.address_name
        ? address.road_address.address_name
        : address.address && address.address.address_name
          ? address.address.address_name
          : "주소 검색 결과";

      return {
        title: address.address_name || detail,
        address: detail,
        lon: Number(address.x),
        lat: Number(address.y)
      };
    }

    function renderSearchResults(results, onSelect = selectSearchResult) {
      searchResults.textContent = "";

      if (!results.length) {
        const empty = document.createElement("div");
        empty.className = "search-empty";
        empty.textContent = "검색 결과가 없습니다.";
        searchResults.appendChild(empty);
        searchResults.hidden = false;
        return;
      }

      results.slice(0, 20).forEach((result) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "search-result";
        button.setAttribute("role", "option");

        const title = document.createElement("span");
        title.className = "search-result-title";
        title.textContent = result.title;

        const address = document.createElement("span");
        address.className = "search-result-address";
        address.textContent = result.address;

        button.appendChild(title);
        button.appendChild(address);
        button.addEventListener("click", () => onSelect(result));
        searchResults.appendChild(button);
      });

      searchResults.hidden = false;
    }

    function searchLocal(
      query,
      onSelect = selectSearchResult,
      manageSearchButton = true,
      selectFirst = false
    ) {
      const { placesService, geocoderService, status: searchStatus } = getServices();
      if (!placesService || !geocoderService) {
        setStatus("카카오 장소·주소 검색이 아직 준비되지 않았습니다.");
        return;
      }

      const requestId = ++searchRequestId;
      const collected = [];
      let remaining = 2;
      let failed = false;

      if (manageSearchButton) {
        searchSubmit.disabled = true;
      }
      setStatus(`카카오 장소·주소 검색 중: ${query}`);

      const finish = () => {
        if (requestId !== searchRequestId) {
          return;
        }

        remaining -= 1;
        if (remaining > 0) {
          return;
        }

        const unique = new Map();
        collected.forEach((result) => {
          if (!Number.isFinite(result.lon) || !Number.isFinite(result.lat)) {
            return;
          }
          const key = `${result.lon.toFixed(7)},${result.lat.toFixed(7)},${result.title}`;
          if (!unique.has(key)) {
            unique.set(key, result);
          }
        });

        const results = Array.from(unique.values());
        if (selectFirst && results.length) {
          searchResults.hidden = true;
          if (manageSearchButton) {
            searchSubmit.disabled = false;
          }
          onSelect(results[0]);
          return;
        }
        renderSearchResults(results, onSelect);
        if (manageSearchButton) {
          searchSubmit.disabled = false;
        }
        setStatus(failed && !results.length
          ? "카카오 장소·주소 검색에 실패했습니다."
          : `카카오 장소·주소 검색 결과: ${results.length}개`);
      };

      placesService.keywordSearch(query, (data, status) => {
        if (requestId !== searchRequestId) {
          return;
        }
        if (status === searchStatus.OK) {
          data.forEach((place) => collected.push(normalizePlaceResult(place)));
        } else if (status === searchStatus.ERROR) {
          failed = true;
        }
        finish();
      });

      geocoderService.addressSearch(query, (data, status) => {
        if (requestId !== searchRequestId) {
          return;
        }
        if (status === searchStatus.OK) {
          data.forEach((address) => collected.push(normalizeAddressResult(address)));
        } else if (status === searchStatus.ERROR) {
          failed = true;
        }
        finish();
      });
    }

    function cancel() {
      searchRequestId += 1;
      searchResults.hidden = true;
      // A superseded request cannot re-enable the main search button.
      // Release it here once services are ready, including route-input resets.
      const services = getServices();
      searchSubmit.disabled = !services.placesService || !services.geocoderService;
    }

    searchForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const query = searchQuery.value.trim();
      if (!query) {
        searchQuery.focus();
        return;
      }
      searchLocal(query);
    });
    searchQuery.addEventListener("input", () => {
      searchClear.disabled = !searchQuery.value;
    });
    searchQuery.addEventListener("keydown", (event) => {
      if (event.key === "Escape") searchResults.hidden = true;
    });
    searchClear.addEventListener("click", () => {
      cancel();
      searchQuery.value = "";
      searchResults.textContent = "";
      searchClear.disabled = true;
      searchQuery.focus();
    });

    return { search: searchLocal, cancel };
};
