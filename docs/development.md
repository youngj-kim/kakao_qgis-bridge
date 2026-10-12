# 개발 구조와 메모

이 문서는 유지보수와 개발을 위한 코드 구조·구현 메모를 모았습니다. 설치와 사용은 [README](../README.md), 버전별 변경은 [CHANGELOG](../CHANGELOG.md)를 참고하세요.

## 폴더 구조

```text
kakao_qgis_bridge/
  __init__.py
  metadata.txt
  plugin.py
  dock_widget.py
  external_bridge.py
  mobility.py
  mobility_client.py
  route_controller.py
  viewer_adapter.py
  sync_controller.py
  style_factory.py
  display_layers.py
  history_repository.py
  history_operations.py
  history_import_service.py
  history_export_service.py
  history_ui_controller.py
  history_export_controller.py
  history_formats.py
  history_values.py
  history_validation.py
  history_export.py
  viewer_page.py
  route_comparison.py
  route_comparison_dialog.py
  compat.py
  settings.py
  settings.example.json
  web/
    kakao_viewer.html
    viewer_search.js
    viewer_guidance.js
    viewer_history.js
    viewer_route_input.js
    viewer_sync.js
docs/
  usage.md
  screenshots/
README.md
```

## 핵심 파일 역할

`kakao_qgis_bridge/metadata.txt`

QGIS 플러그인 관리자에서 읽는 플러그인 메타데이터입니다. 이름, 버전, 최소 QGIS 버전, 설명, 실험 상태 등을 정의합니다.

`kakao_qgis_bridge/__init__.py`

QGIS가 플러그인을 로드할 때 호출하는 `classFactory(iface)` 진입점입니다. 실제 플러그인 클래스인 `KakaoQgisBridgePlugin`을 생성해 반환합니다.

`kakao_qgis_bridge/plugin.py`

QGIS와 직접 연결되는 메인 플러그인 코드입니다. 메뉴/툴바 버튼을 만들고, Dock Widget을 열고 닫으며, QGIS 기본 탐색 기능으로 변경된 캔버스 중심 좌표를 현재 프로젝트 CRS에서 EPSG:4326으로 변환합니다. Roadview 상태를 `Kakao Roadview Position` 메모리 포인트 레이어로 관리합니다.

`kakao_qgis_bridge/dock_widget.py`

QGIS 보조 창인 `QDockWidget`을 정의합니다. 내부에 `QWebEngineView`를 만들고, 공통 조립 함수로 HTML을 로드한 뒤 `window.centerKakaoMap(lon, lat, updateRoadview, metersPerPixel)`로 중심·줌·로드뷰 갱신 정책을 전달합니다. `QWebChannel`을 통해 Kakao 지도 위치·줌과 Roadview 위치·방향 정보를 다시 Python으로 전달합니다. Qt WebEngine을 사용할 수 없는 QGIS 3 환경에서는 외부 브라우저 연동 안내와 실행 버튼을 표시합니다.

`kakao_qgis_bridge/external_bridge.py`

외부 브라우저 연동 모드에서 사용하는 로컬 HTTP 브리지 서버입니다. 기본 `http://localhost:8081/`에서 Kakao Viewer HTML을 제공하고 포트 사용 중에는 8082를 시도합니다. 브라우저와 QGIS 사이의 중심 좌표·지상 해상도, Roadview 상태, 경로 요청과 이력을 인증된 JSON API로 중계하며 상태 스냅샷과 이벤트 누락 복구를 지원합니다.

`kakao_qgis_bridge/mobility.py`, `mobility_client.py`

경로 요청 검증·쿼리 생성·응답 파싱과 Qt 네트워크 요청을 분리해 관리합니다. QGIS와 무관한 검증·파싱 로직은 일반 Python 단위 테스트로 확인할 수 있습니다.

`kakao_qgis_bridge/sync_controller.py`

QGIS 캔버스와 Kakao Viewer 사이의 양방향 위치·줌 동기화, 좌표계 변환과 지상 해상도 계산, 확대·축소/이동 구분 및 상태 비교 기반 역방향 동기화 가드를 담당합니다.

`kakao_qgis_bridge/style_factory.py`

경로 선, 안내·GPX·핀 분류 renderer와 로드뷰 radar 심볼을 생성합니다. 각 호출은 새로운 QGIS 객체를 반환하며 SVG 인코딩 문자열만 캐시합니다. 저장소와 내보내기 서비스도 이 팩토리를 공유합니다. UI·프로젝트·레이어 수명과 데이터 변경은 담당하지 않습니다.

`kakao_qgis_bridge/display_layers.py`

현재 경로·안내·출발/도착/경유지 핀·로드뷰 표시 레이어를 생성·갱신·제거하고 feature ID와 범례 category 캐시를 관리합니다. 프로젝트와 스타일 팩토리를 주입받으며 지도 이동·뷰어 상태·이력 저장소와 UI는 직접 처리하지 않습니다. 종료할 때 자신이 보관한 표시 레이어만 제거합니다.

`kakao_qgis_bridge/history_repository.py`, `history_operations.py`, `history_import_service.py`, `history_export_service.py`, `history_formats.py`, `history_export.py`, `history_values.py`

경로·안내 이력의 메모리 레이어와 조회·데이터 삭제는 저장소가 관리합니다. 이력 파일 읽기·필드 복원은 가져오기 서비스가, GeoPackage/GeoJSON/Shapefile/GPX 파일 작성과 출력 스타일 저장은 내보내기 서비스가 담당합니다. `history_formats.py`는 공통 파일명·필드 이름 대응, `history_export.py`는 GPX XML 작성기, `history_values.py`는 내보내기와 뷰어 복원이 공유하는 값 변환 함수입니다. 대화상자·이력 선택·활성 경로와 뷰어 갱신·결과 안내는 플러그인이 담당합니다.

대화상자와 이력 UI의 세부 조정은 `history_ui_controller.py`와 `history_export_controller.py`에 분리되어 있습니다. 플러그인은 진입점과 지도 표시·웹 전달 콜백을 연결하며, 이력 컨트롤러는 목록·선택·복원·삭제를, 내보내기 컨트롤러는 형식·파일 선택·확인·완료 안내를 담당합니다.

`history_operations.py`는 이력 변경 전 편집 가능 여부, 실제 반영 건수와 실패 후 보상 복구를 확인합니다. 복구되지 않은 부분 변경은 오류로 안내하고 추가 이력 변경을 차단하며, 보관용 내보내기는 유지합니다. 이는 두 레이어에 대한 DB 트랜잭션이 아닙니다.

`kakao_qgis_bridge/web/kakao_viewer.html`

Kakao Maps JavaScript API를 로드하는 실제 웹 뷰어입니다. Kakao Map, Marker, Roadview, RoadviewClient를 생성하고 QGIS에서 전달된 좌표를 기준으로 지도 중심과 로드뷰를 갱신합니다. 지도의 `drag`/`dragend`와 Roadview의 `position_changed` 이벤트가 발생하면 변경 위치를 QGIS로 전달합니다. `services.Places`와 `services.Geocoder`로 장소 및 주소를 검색합니다. 지도·로드뷰 배치 전환, 분할선 크기 조절, 전체화면 전환, 창 크기 변경 시 Kakao Map/Roadview relayout을 처리합니다.

검색·안내·이력·경로 입력은 각각 `viewer_search.js`, `viewer_guidance.js`, `viewer_history.js`, `viewer_route_input.js`가 담당하며 `viewer_page.py`가 도크와 외부 브라우저에 같은 모듈을 inline 삽입합니다. HTML은 SDK 초기화·지도/로드뷰 이동·줌·레이아웃과 브리지 연결을 유지합니다.

`kakao_qgis_bridge/settings.py`

Kakao JavaScript 키, Mobility REST API 키와 WebEngine 기준 URL을 관리하는 설정 모듈입니다. JavaScript 키 우선순위는 환경변수 `KAKAO_MAP_JAVASCRIPT_KEY`, QGIS 사용자 설정, 기존 `kakao_qgis_bridge/settings.json` 순서입니다. REST 키는 환경변수 `KAKAO_REST_API_KEY`, QGIS 사용자 설정 순서이며 기준 URL은 `KAKAO_MAP_BASE_URL`로 변경할 수 있습니다.

`kakao_qgis_bridge/settings.example.json`

로컬 설정 파일 예시입니다. 실제 키를 넣은 `settings.json`은 `.gitignore`에 포함되어 저장소에 커밋되지 않도록 했습니다.

## 개발 메모

- Kakao 지도는 QGIS 레이어로 추가하지 않고 WebEngine 안에서만 표시합니다.
- QGIS 캔버스의 현재 목적 CRS를 기준으로 중심 좌표를 읽고, `QgsCoordinateTransform`으로 EPSG:4326 변환을 수행합니다.
- 연속 드래그 중에는 350ms 디바운스를 적용해 Kakao Roadview 요청이 과도하게 발생하지 않도록 합니다.
- Python에서 JavaScript로 값을 넘길 때는 `QWebEnginePage.runJavaScript()`를 사용합니다.
- JavaScript에서 Python으로 값을 넘길 때는 Qt의 `QWebChannel`을 사용합니다.
- 역방향 이동·줌을 적용한 뒤 중심·CRS·해상도가 예상 상태와 일치하는 반향만 억제합니다. 고정 600ms 차단 방식은 사용하지 않습니다.
- 확대·축소는 지도 중심과 지상 해상도를 전달하되 Roadview 촬영 위치를 바꾸지 않습니다. 카카오 일반지도 확대 단계 1~14 밖의 축척은 맞출 수 없고 QGIS 축척 잠금은 존중합니다.
- 과거 촬영본 목록은 JavaScript API에서 제공되지 않으므로 공식 카카오맵 Roadview 링크에서 선택합니다.
- Local 검색은 이미 로드한 Kakao Maps JavaScript `services` 라이브러리를 사용하므로 별도의 REST API 키가 필요하지 않습니다.
- Roadview 메모리 레이어는 EPSG:4326 포인트 1개를 반투명 원과 시야 부채꼴로 구성된 레이더형 마커로 표시합니다.
- 레이더형 마커는 `pan` 필드를 회전각으로 사용해 Roadview 시선 방향을 표시합니다.
- 메모리 레이어 필드는 `pano_id`, `longitude`, `latitude`, `pan`, `tilt`, `zoom`입니다.
- 경로 레이어는 EPSG:4326 LineString이며 거리·시간, 안내 개수, 경로·차량 옵션과 표시용 `result_summary` 속성을 저장합니다.
- 새 경로를 생성하면 이전 `Kakao Mobility Route` 임시 레이어를 교체합니다.
- 경로 지점 레이어는 EPSG:4326 Point이며 `point_id`, `role`, `longitude`, `latitude` 속성을 저장합니다.
- 출발지는 녹색, 도착지는 빨간색 위치 핀으로 분류 렌더링되며 핀 끝이 실제 좌표에 맞춰집니다.
- 경유지는 주황색 위치 핀으로 표시되며 추가된 순서대로 Kakao Mobility API에 전달됩니다.
- 출발지·도착지를 교환하면 입력값, 확정 좌표, QGIS 핀 역할이 함께 바뀝니다.
- 경유지 순서를 변경해도 각 지점의 좌표와 핀은 유지되며 변경된 화면 순서대로 API에 전달됩니다.
- 선택한 회피 옵션은 `|`로 연결해 Kakao Mobility API에 전달하고 경로 레이어의 `avoid` 필드에도 저장합니다.
- 차량 설정은 Kakao Mobility API의 `car_type`, `car_fuel`, `car_hipass`에 전달하고 경로 레이어 속성에도 저장합니다.
- 경로 입력창의 장소·주소 검색은 500ms 동안 입력이 멈추면 실행되며, 좌표 입력은 즉시 해석됩니다.
- 경로 입력을 변경하거나 초기화하면 해당 위치 핀도 갱신됩니다.
- 경로 안내 레이어는 EPSG:4326 Point이며 `sequence`, `section_no`, `guide_type`, `category`, `guidance`, 구간·누적 거리와 시간, `road_index` 속성을 저장합니다.
- 안내 유형은 출발·도착·경유지·직진·좌회전·우회전·유턴·회전교차로·진출입·기타로 분류합니다. 현재 안내 레이어의 출발·도착·경유 범주는 렌더링만 꺼 중복 핀을 숨기며 피처·속성·안내 선택은 유지합니다. 독립적인 이력 레이어의 기본 스타일은 변경하지 않습니다.
- 새 경로를 생성하면 이전 `Kakao Route Guidance` 레이어와 Dock 안내 목록을 현재 결과로 교체합니다.
- 성공한 경로 검색은 표시용 레이어와 별도로 세션 이력에 누적되며 각 검색에는 UUID 형식의 `history_id`와 ISO 8601 검색 시각이 부여됩니다.
- GeoPackage에는 EPSG:4326 LineString인 `kakao_route_history`와 Point인 `kakao_guidance_history`가 생성됩니다.
- 두 이력 레이어는 `history_id`로 연결되며 출발지·도착지·경유지 입력값, Kakao 응답의 `route_id`, 경로 옵션, 차량 설정, 거리·시간 및 순서별 안내 속성을 함께 저장합니다.
- 경로 이력의 `guidance_count`에는 안내 포인트 수를, `result_summary`에는 `69분 · 31.7 km · 소형 · 안내 32개` 형식의 속성 테이블용 요약을 저장합니다.
- 이력 스키마 버전은 `schema_ver=2`이며 기존 GeoPackage에 새 필드가 없으면 다음 저장 시 자동으로 추가합니다. 기존 레코드의 새 필드는 `NULL`로 유지됩니다.
- 같은 GeoPackage에 반복 저장할 때 기존 `history_id`를 확인해 현재 세션의 미저장 피처만 추가합니다. 파일 안의 다른 레이어는 유지됩니다.
- `layer_styles` 테이블에 경로선과 안내 분류 렌더러를 기본 QML 스타일로 함께 저장하므로 QGIS에서 레이어를 다시 추가할 때 심볼이 자동 적용됩니다.
- 안내 SVG는 QML 스타일 안에 Base64로 내장되므로 GeoPackage를 다른 PC로 옮겨도 별도 SVG 파일 없이 같은 심볼을 사용할 수 있습니다.
- GeoJSON은 여러 레이어를 담는 컨테이너가 아니므로 경로 LineString과 안내 Point를 별도 파일로 내보내며 두 파일은 `history_id`로 연결됩니다.
- GeoJSON은 RFC 7946, EPSG:4326, 소수점 8자리로 출력하고 파일별 Base64 SVG QML 스타일을 함께 생성합니다.
- Shapefile은 필드명과 문자열 길이 제약이 있으므로 `history_id`는 `hist_id`, `guidance_count`는 `guide_cnt`처럼 짧은 필드명으로 변환해 내보냅니다.
- Shapefile의 긴 문자열은 254자 기준으로 잘릴 수 있으므로 전체 경유지 JSON이나 긴 설명을 보존해야 할 때는 GeoPackage 또는 GeoJSON을 우선 사용합니다.
- GPX는 한 파일 안에 경로 선형을 `trk`와 `rte`로 함께 저장하고, 출발지·도착지·경유지·안내 지점을 `wpt`로 저장합니다.
- GPX 내보내기 시 QGIS 스타일 복원을 위해 `*_tracks.qml`, `*_routes.qml`, `*_waypoints.qml` 파일도 함께 생성합니다.
- GPX 웨이포인트 QML은 `type` 필드를 기준으로 출발지·도착지·경유지·안내 유형을 분류 렌더링합니다.
- GPX를 QGIS에 직접 드래그하면 QGIS 기본 스타일이 적용될 수 있으므로, 스타일 복원이 필요하면 플러그인의 `GPX 스타일 적용해서 불러오기...` 메뉴를 사용합니다.
- GPX의 표준 필드로 담기 어려운 `history_id`, 경로 옵션, 거리·시간, 안내 순번 등은 `kakao:*` 확장 태그로 기록합니다.
- Dock의 경로 이력 탭은 세션 메모리 이력을 기준으로 표시되며, 선택한 `history_id`의 경로 LineString과 안내 Point를 현재 표시 레이어로 재구성합니다.
- QGIS 3 외부 브라우저 모드에서도 경로 결과의 `path` 좌표를 전달해 Kakao 지도 위에 현재 경로선을 표시합니다.
- QGIS 4 Dock 모드의 `외부 브라우저 연동창` 버튼은 같은 로컬 브리지 서버를 사용해 Dock과 별도 브라우저 창을 병행할 수 있게 합니다.
- `이력` 버튼은 `refreshRouteHistory()` 요청으로 QGIS의 최신 세션 이력을 다시 받아오며, QGIS 4 WebChannel과 QGIS 3 외부 브리지 모두 같은 흐름을 사용합니다.
- 안내 패널의 경로 개요는 경로 생성 또는 이력 선택 시 전달되는 `origin`, `waypoints`, `destination` payload를 기준으로 표시합니다.
- `경로 이력 불러오기...`는 GeoPackage의 `kakao_route_history`, `kakao_guidance_history` 레이어 또는 GeoJSON/Shapefile의 `*_routes`, `*_guidance` 짝 파일을 현재 세션 이력으로 병합합니다.
- 불러올 때 이미 현재 세션에 있는 `history_id`는 건너뛰어 중복 이력을 만들지 않습니다.
- 이력의 `불러오기` 기능은 저장된 출발지·도착지·경유지 좌표와 라벨, 경로 유형, 회피 옵션, 차량 설정을 경로 입력 UI로 복원합니다.
- 현재 선택된 이력을 삭제하면 세션 이력 레이어뿐 아니라 현재 표시용 경로·안내 임시 레이어, Dock 안내 목록, Kakao 지도 경로선도 함께 비웁니다.
- 선택 이력 내보내기는 전체 세션 저장과 같은 스키마를 사용하되 선택된 `history_id` 1건과 연결된 안내 포인트만 대상으로 합니다.
- 저장하지 않은 세션 이력은 플러그인을 해제하거나 QGIS를 종료하면 제거됩니다.

## 개발 기록과 검증 문서

- [추가 리팩토링 정리와 업로드 전 확인](refactoring-finalization.md)

- [날짜별 개발 이력](development-history.md)
- [리팩토링 진행 기록](refactoring-progress.md)
- [배포 체크리스트](release-checklist.md)
- [경로 핀 위치와 중복 표시 수정](route-points-fix.md)
- [지도 줌·로드뷰 동기화 정책](zoom-roadview-policy.md)
- [이력 가져오기 검증](history-import-validation-review.md)
- [내보내기 검증](export-validation.md)
