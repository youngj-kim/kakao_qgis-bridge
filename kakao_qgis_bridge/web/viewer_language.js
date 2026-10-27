/* Translate plugin controls only; preserve SDK labels and user content. */
(function () {
  "use strict";
  const translations = {
  "Collapse ▴": "탐색창 접기 ▴",
  "Search": "검색",
  "Toggle fullscreen": "전체화면 전환",
  "Clear search": "검색 지우기",
  "Toggle Roadview roads": "로드뷰 촬영 도로 표시 켜기/끄기",
  "Show Roadview roads": "로드뷰 도로 표시",
  "Show results": "검색 결과 펼치기",
  "Route avoidance options": "경로 회피 옵션",
  "Avoid 0": "회피 0",
  "Vehicle settings": "차량 설정",
  "Vehicle": "차량",
  "Add waypoint": "경유지 추가",
  "+ Waypoint": "+ 경유지",
  "Use map center as origin": "현재 지도 중심을 출발지로 사용",
  "Here": "현위치",
  "Use map center as destination": "현재 지도 중심을 도착지로 사용",
  "Create route": "경로 생성",
  "Open route history": "경로 이력 열기",
  "History": "이력",
  "Swap origin and destination": "출발지와 도착지 바꾸기",
  "Reset route": "경로 입력 초기화",
  "Directions": "안내",
  "Collapse directions / history": "안내/이력 접기",
  "Swap map and Roadview": "지도와 로드뷰 위치 전환",
  "Open linked browser": "외부 연동 창 열기",
  "Historical imagery in Kakao Map": "카카오맵에서 과거 촬영 선택",
  "Expand ▾": "탐색창 펼치기 ▾",
  "Expand directions / history": "안내/이력 펼치기",
  "Load history": "이력 불러오기",
  "Deselect all": "전체 해제",
  "Select all": "전체 선택",
  "Delete all": "전체 삭제",
  "Save selected": "선택 저장",
  "Load": "불러오기",
  "Delete": "삭제",
  "Export": "내보내기",
  "Hide Roadview roads": "로드뷰 도로 숨기기",
  "Hide": "접기",
  "Show": "펼치기",
  "Open linked browser...": "외부 브라우저 연동 창 열기...",
  "Configure Kakao JavaScript API key...": "Kakao JavaScript API 키 설정...",
  "Configure Kakao REST API key...": "Kakao REST API 키 설정...",
  "Load route history...": "경로 이력 불러오기...",
  "Compare GPKG routes...": "GPKG 경로 비교...",
  "Load GPX with styles...": "GPX 스타일 적용해서 불러오기...",
  "Save route history as GeoPackage...": "경로 이력 GeoPackage 저장...",
  "Export route and directions as GeoJSON...": "경로·안내 이력 GeoJSON 내보내기...",
  "Export route and directions as Shapefile...": "경로·안내 이력 Shapefile 내보내기...",
  "Export route and directions as GPX...": "경로·안내 이력 GPX 내보내기...",
  "Open Kakao Map": "카카오맵 열기",
  "Open Roadview": "로드뷰 열기",
  "Open GPKG…": "GPKG 열기…",
  "Show both routes": "두 경로 지도에 표시",
  "Clear comparison": "비교 표시 지우기",
  "Map": "지도",
  "Route": "경로",
  "Origin": "출발",
  "Destination": "도착",
  "Map above / Roadview below": "지도 위 / 로드뷰 아래",
  "Roadview above / Map below": "로드뷰 위 / 지도 아래",
  "Map left / Roadview right": "지도 좌 / 로드뷰 우",
  "Roadview left / Map right": "로드뷰 좌 / 지도 우",
  "Roadmap": "일반지도",
  "Aerial": "항공영상",
  "Aerial + labels": "항공영상+지명",
  "Recommended": "추천 경로",
  "Fastest": "최단 시간",
  "Shortest": "최단 거리",
  "Toll roads": "유료도로",
  "Motorways": "자동차전용도로",
  "Ferries": "페리",
  "School zones": "어린이보호구역",
  "U-turns": "유턴",
  "Vehicle type": "차종",
  "Fuel": "유종",
  "Small": "소형",
  "Medium": "중형",
  "Large": "대형",
  "Large truck": "대형 화물",
  "Special truck": "특수 화물",
  "Compact": "경차",
  "Motorcycle": "이륜차",
  "Gasoline": "휘발유",
  "Diesel": "경유",
  "Hi-pass": "하이패스",
  "Search address or place": "주소 또는 장소 검색",
  "Address, place or longitude,latitude": "주소·장소 또는 경도,위도",
  "Map and Roadview layout": "지도와 로드뷰 배치",
  "Route type": "경로 유형"
};
  const reverse = Object.fromEntries(Object.entries(translations).map(([en, ko]) => [ko, en]));
  const storageKey = "kakao_qgis_bridge/ui_language";
  let language = "ko";
  try { language = localStorage.getItem(storageKey) === "en" ? "en" : "ko"; } catch (_) {}
  function translate(value) {
    const english = reverse[value] || value;
    const avoid = english.match(/^Avoid (\d+)$/) || value.match(/^회피 (\d+)$/);
    if (avoid) return (language === "en" ? "Avoid " : "회피 ") + avoid[1];
    const results = english.match(/^(Hide|Show) results \((\d+)\)$/) || value.match(/^검색 결과 (\d+)개 (접기|펼치기)$/);
    if (results) {
      const korean = value.startsWith("검색 결과");
      const count = korean ? results[1] : results[2];
      const expanded = korean ? results[2] === "접기" : results[1] === "Hide";
      return language === "en" ? (expanded ? "Hide" : "Show") + " results (" + count + ")" : "검색 결과 " + count + "개 " + (expanded ? "접기" : "펼치기");
    }
    return language === "en" ? english : (translations[english] || value);
  }
  const toggle = document.getElementById("viewer-language-toggle");
  function refresh() {
    document.querySelectorAll("#viewer button, #search-panel label, #search-panel option, #search-panel input, #search-panel select").forEach(button => {
      if (button === toggle) return;
      // Preserve any icons or nested elements inside buttons.
      button.childNodes.forEach(node => {
        if (node.nodeType === 3) {
          const next = translate(node.nodeValue.trim());
          if (next !== node.nodeValue.trim()) node.nodeValue = next;
        }
      });
      ["title", "aria-label", "placeholder"].forEach(attribute => {
        const value = button.getAttribute(attribute);
        if (value) { const next = translate(value); if (next !== value) button.setAttribute(attribute, next); }
      });
    });
    toggle.textContent = language === "en" ? "KR" : "EN";
    const label = language === "en" ? "한국어 버튼으로 전환" : "Switch buttons to English";
    toggle.setAttribute("aria-label", label);
    toggle.setAttribute("title", label);
  }
  toggle.addEventListener("click", () => {
    language = language === "en" ? "ko" : "en";
    try { localStorage.setItem(storageKey, language); } catch (_) {}
    refresh();
  });
  // Other controllers rebuild button labels and history actions as state changes.
  if (typeof MutationObserver !== "undefined") {
    const observer = new MutationObserver(() => {
      observer.disconnect();
      refresh();
      observe();
    });
    function observe() { observer.observe(document.getElementById("viewer"), {subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["title", "aria-label", "placeholder"]}); }
    refresh();
    observe();
  }
})();
