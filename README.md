# Kakao QGIS Bridge

QGIS 3.34 LTR 이상과 QGIS 4.0 / Qt 6 환경을 함께 고려하는 Python 플러그인입니다. Plugin Builder를 사용하지 않고 직접 관리할 수 있도록 `metadata.txt`, `__init__.py`, 플러그인 클래스, Dock Widget, Kakao Maps JavaScript API HTML 뷰어를 작게 분리했습니다.

이 플러그인은 Kakao 지도 타일 URL을 추출하거나 QGIS XYZ/TMS 배경지도로 등록하지 않습니다. 대신 QGIS Dock Widget 안의 `QWebEngineView`에서 Kakao Maps JavaScript API를 로드하고, QGIS 기본 탐색 기능으로 변경된 캔버스 중심 좌표를 EPSG:4326으로 변환해 Kakao Map과 Roadview 중심으로 전달합니다.

## 현재 단계

- Plugin Builder 없는 최소 QGIS 플러그인 구조
- QGIS 메뉴/툴바 액션 등록
- Dock Widget 생성
- Dock 내부 `QWebEngineView` 표시
- Kakao Maps JavaScript API 지도 로드
- QGIS 캔버스 중심 좌표를 EPSG:4326으로 변환
- QGIS 기본 이동·확대·축소 후 Kakao 지도와 Roadview 동기화
- 변환 좌표를 WebEngine의 Kakao 지도/로드뷰로 전달
- Kakao 지도 드래그 중 QGIS 캔버스 중심 실시간 역방향 동기화
- Roadview 위치 이동 시 QGIS 캔버스 중심 역방향 동기화
- QGIS 3에서 Qt WebEngine 없이 외부 브라우저 연동 모드 지원
- QGIS 4에서도 Dock 하단 버튼으로 외부 브라우저 연동 창 실행 지원
- 현재 Roadview 위치를 카카오맵 서비스에서 열어 과거 촬영본 선택
- Kakao Local 장소·주소 검색과 결과 선택 이동
- 지도·로드뷰 상하/좌우 배치 전환, 중간 분할선 크기 조절, 화면 내부 전체화면 전환
- QGIS 4 Dock/분리창과 QGIS 3 외부 브라우저에서 반응형 중앙 정렬 뷰어 지원
- Roadview 위치·방향·기울기·확대 정보를 QGIS 메모리 레이어로 표시
- Kakao Mobility 자동차 경로를 QGIS 임시 LineString 레이어로 표시
- 경로 출발지와 도착지를 QGIS 녹색·빨간색 위치 핀으로 표시
- 추천·최단 시간·최단 거리 경로 유형과 최대 5개 경유지 지원
- 출발지·도착지 교환과 경유지 위·아래 순서 변경
- 유료도로·자동차전용도로·페리·어린이보호구역·유턴 회피 옵션
- 차종·유종·하이패스 차량 설정
- 회전·직진·진출입 순서별 안내를 QGIS 포인트 레이어와 Dock 목록으로 표시
- 안내 패널에서 현재 경로의 출발지·경유지·도착지 개요 표시

## 폴더 구조

```text
kakao_qgis_bridge/
  __init__.py
  metadata.txt
  plugin.py
  dock_widget.py
  external_bridge.py
  settings.py
  settings.example.json
  web/
    kakao_viewer.html
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

QGIS 보조 창인 `QDockWidget`을 정의합니다. 내부에 `QWebEngineView`를 만들고, HTML 템플릿을 로드한 뒤 Python에서 JavaScript 함수 `window.centerKakaoMap(lon, lat)`를 호출합니다. `QWebChannel`을 통해 Kakao 지도 위치와 Roadview 위치·방향 정보를 다시 Python으로 전달합니다. Qt WebEngine을 사용할 수 없는 QGIS 3 환경에서는 외부 브라우저 연동 안내와 실행 버튼을 표시합니다.

`kakao_qgis_bridge/external_bridge.py`

QGIS 3 외부 브라우저 연동 모드에서 사용하는 로컬 HTTP 브리지 서버입니다. `http://localhost:8081/`에서 Kakao Viewer HTML을 제공하고, 브라우저와 QGIS 사이의 중심 좌표, Roadview 상태, 경로 요청, 경로 이력 이벤트를 JSON API로 중계합니다.

`kakao_qgis_bridge/web/kakao_viewer.html`

Kakao Maps JavaScript API를 로드하는 실제 웹 뷰어입니다. Kakao Map, Marker, Roadview, RoadviewClient를 생성하고 QGIS에서 전달된 좌표를 기준으로 지도 중심과 로드뷰를 갱신합니다. 지도의 `drag`/`dragend`와 Roadview의 `position_changed` 이벤트가 발생하면 변경 위치를 QGIS로 전달합니다. `services.Places`와 `services.Geocoder`로 장소 및 주소를 검색합니다. 지도·로드뷰 배치 전환, 분할선 크기 조절, 전체화면 전환, 창 크기 변경 시 Kakao Map/Roadview relayout을 처리합니다.

`kakao_qgis_bridge/settings.py`

Kakao JavaScript 키, Mobility REST API 키와 WebEngine 기준 URL을 관리하는 설정 모듈입니다. JavaScript 키 우선순위는 환경변수 `KAKAO_MAP_JAVASCRIPT_KEY`, QGIS 사용자 설정, 기존 `kakao_qgis_bridge/settings.json` 순서입니다. REST 키는 환경변수 `KAKAO_REST_API_KEY`, QGIS 사용자 설정 순서이며 기준 URL은 `KAKAO_MAP_BASE_URL`로 변경할 수 있습니다.

`kakao_qgis_bridge/settings.example.json`

로컬 설정 파일 예시입니다. 실제 키를 넣은 `settings.json`은 `.gitignore`에 포함되어 저장소에 커밋되지 않도록 했습니다.

## Kakao API 키 설정

### 키 발급 및 앱 등록

1. [Kakao Developers](https://developers.kakao.com/)에 카카오 계정으로 로그인하고 개발자 등록을 완료합니다.
2. 앱 관리 화면의 전체 앱 목록에서 `앱 생성`을 선택하고 앱 이름, 회사·단체명, 카테고리와 서비스 또는 프로젝트를 나타내는 대표 도메인을 입력합니다.
3. 생성한 앱에서 `앱 > 플랫폼 키`로 이동합니다. 앱 생성 시 JavaScript 키와 REST API 키가 함께 생성됩니다.
4. `JavaScript 키`를 선택하고 `JavaScript SDK 도메인`에 기본 주소인 `http://localhost:8081`을 등록합니다.
5. 플랫폼 키 화면의 JavaScript 키는 Kakao Map·Roadview·Local 검색에, REST API 키는 Kakao Mobility 경로 탐색에 사용합니다.
6. 플러그인 최초 실행 입력창에 JavaScript 키를 입력하고, 최초 경로 생성 입력창에는 REST API 키를 입력합니다.

이 플러그인은 어드민 키를 사용하지 않습니다. 어드민 키는 권한이 크므로 플러그인에 입력하거나 저장소에 커밋하지 마세요. 자세한 최신 절차는 [Kakao API 시작하기](https://developers.kakao.com/docs/ko/tutorial/start)와 [Kakao 지도 Web API 가이드](https://apis.map.kakao.com/web/guide/)를 참고하세요.

### 최초 실행 입력창

툴바의 `Kakao Map / Roadview`를 처음 실행하면 JavaScript 키 입력창이 표시됩니다. 입력값은 소스 코드나 플러그인 폴더가 아니라 QGIS 사용자 설정에 저장되며, 다음 실행부터 자동으로 사용됩니다.

키를 바꾸려면 QGIS의 `플러그인 > Kakao QGIS Bridge > Kakao JavaScript API 키 설정...` 메뉴를 사용합니다. 입력창은 키를 가려서 표시하지만 QGIS 설정 저장소 자체가 암호화되는 것은 아니므로, Kakao Developers에서 `http://localhost:8081` 도메인 제한을 반드시 함께 설정하세요.

환경변수를 사용하는 운영 환경에서는 아래 방식도 계속 지원하며 입력창 저장값보다 우선 적용됩니다.

### Kakao Mobility REST API 키

경로 탐색은 JavaScript 키가 아닌 Kakao Developers의 REST API 키를 사용합니다. 처음 `경로 생성`을 실행하면 별도의 REST 키 입력창이 표시되며 QGIS 사용자 설정에 저장됩니다. 이후에는 `플러그인 > Kakao QGIS Bridge > Kakao REST API 키 설정...` 메뉴에서 변경할 수 있습니다.

Kakao Developers 앱에서 Kakao Mobility 길찾기 사용 권한과 관련 제품 설정이 활성화되어 있어야 합니다.
REST API 키가 저장되는 QGIS 설정 저장소는 암호화되지 않으므로 공유 PC에서는 환경변수 방식을 권장합니다.

### Windows PowerShell

현재 터미널 세션에서만 사용할 때:

```powershell
$env:KAKAO_MAP_JAVASCRIPT_KEY="YOUR_KAKAO_MAP_JAVASCRIPT_KEY"
$env:KAKAO_REST_API_KEY="YOUR_KAKAO_REST_API_KEY"
$env:KAKAO_MAP_BASE_URL="http://localhost:8081/kakao_qgis_bridge/"
```

사용자 환경변수로 저장할 때:

```powershell
[Environment]::SetEnvironmentVariable("KAKAO_MAP_JAVASCRIPT_KEY", "YOUR_KAKAO_MAP_JAVASCRIPT_KEY", "User")
[Environment]::SetEnvironmentVariable("KAKAO_REST_API_KEY", "YOUR_KAKAO_REST_API_KEY", "User")
[Environment]::SetEnvironmentVariable("KAKAO_MAP_BASE_URL", "http://localhost:8081/kakao_qgis_bridge/", "User")
```

환경변수를 저장한 뒤에는 QGIS를 완전히 종료했다가 다시 실행하세요.

### 기존 설정 파일에서 이전

기존 `kakao_qgis_bridge/settings.json`이 있으면 최초 입력창에 값이 가려진 상태로 채워집니다. 확인을 누르면 QGIS 사용자 설정으로 이전됩니다.

```json
{
  "kakao_javascript_key": "YOUR_KAKAO_MAP_JAVASCRIPT_KEY"
}
```

## Kakao 플랫폼 도메인 설정

이 플러그인은 `QWebEngineView.setHtml()`의 기준 URL을 `http://localhost:8081/kakao_qgis_bridge/`로 지정합니다. Kakao Developers에서 JavaScript 키의 Web 플랫폼 사이트 도메인에 다음 값을 등록하세요.

```text
http://localhost:8081
```

8081번 포트에서 별도의 로컬 웹 서버를 실행할 필요는 없습니다. 이 주소는 `QWebEngineView` 문서의 기준 URL과 Kakao JavaScript 키의 허용 출처를 일치시키기 위해 사용합니다.

포트를 변경하려면 Windows 사용자 환경변수 `KAKAO_MAP_BASE_URL`을 원하는 기준 URL로 설정합니다. 예를 들어 9000번 포트로 바꾸려면 다음과 같이 설정합니다.

```powershell
[Environment]::SetEnvironmentVariable("KAKAO_MAP_BASE_URL", "http://localhost:9000/kakao_qgis_bridge/", "User")
```

그다음 Kakao Developers의 `앱 > 플랫폼 키 > JavaScript 키 > JavaScript SDK 도메인`에도 경로를 제외한 다음 출처를 등록합니다.

```text
http://localhost:9000
```

환경변수의 프로토콜·호스트·포트와 Kakao Developers 등록값이 일치해야 합니다. 변경 후에는 QGIS를 완전히 종료했다가 다시 실행하세요. 환경변수를 삭제하면 기본값인 8081번 포트로 돌아갑니다.

## 설치 방법

QGIS 플러그인 디렉터리에 `kakao_qgis_bridge` 폴더를 복사하거나 심볼릭 링크로 연결합니다.

일반적인 Windows 개발용 경로 예시는 다음과 같습니다.

```text
%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\kakao_qgis_bridge
%APPDATA%\QGIS\QGIS4\profiles\default\python\plugins\kakao_qgis_bridge
```

QGIS 프로필 경로는 설치 방식이나 프리릴리스 빌드에 따라 다를 수 있습니다. QGIS에서 Python 콘솔을 열 수 있다면 아래 값으로 실제 프로필 루트를 확인할 수 있습니다.

```python
QgsApplication.qgisSettingsDirPath()
```

설치 후 QGIS를 다시 시작하고, 플러그인 관리자에서 `Kakao QGIS Bridge`를 활성화합니다.

## QGIS 3 외부 브라우저 연동 모드

QGIS 4에서는 Dock 내부의 Kakao Map/Roadview 창을 기본 모드로 사용합니다.

QGIS 3에서는 외부 브라우저 연동 모드로 사용할 수 있습니다. 플러그인이 `http://localhost:8081/`에 작은 로컬 브리지 서버를 띄우고, `외부 연동 창 열기` 버튼으로 기본 브라우저의 Kakao Viewer를 엽니다.

외부 브라우저 연동 모드에서도 QGIS 캔버스 중심 좌표는 EPSG:4326으로 변환되어 브라우저 Kakao Map/Roadview로 전달됩니다. 브라우저의 Kakao 지도나 Roadview 위치 이동도 localhost API를 통해 QGIS 캔버스와 Roadview 위치 레이어로 다시 전달됩니다. 단, Dock 내부 렌더링은 사용하지 않으므로 브라우저 창은 QGIS와 별도로 관리됩니다.

Kakao Developers의 JavaScript SDK 허용 도메인에는 아래 값을 등록해야 합니다.

```text
http://localhost:8081
```

## 실행 방법

1. QGIS를 실행합니다.
2. 플러그인 관리자에서 `Kakao QGIS Bridge`를 활성화합니다.
3. 툴바 또는 메뉴에서 `Kakao Map / Roadview` 버튼을 클릭합니다.
4. 최초 실행 입력창에 Kakao JavaScript 키를 넣고 확인합니다.
5. Dock Widget이 열리면 QGIS의 기본 손 도구로 캔버스를 드래그하거나 확대·축소합니다.
6. 이동된 캔버스 중심 좌표가 EPSG:4326으로 변환되어 Kakao Map과 Roadview로 전달됩니다.
7. 상단 Kakao 지도를 드래그하면 QGIS 캔버스 중심도 약 120ms 간격으로 따라 이동합니다.
8. Roadview 안의 이동 화살표로 위치를 바꾸면 QGIS 캔버스 중심도 해당 위치로 이동합니다.
9. 하단의 `카카오맵에서 과거 촬영 선택` 버튼을 누르면 현재 위치의 공식 카카오맵 Roadview가 기본 브라우저에서 열립니다. `외부 브라우저 연동창` 버튼을 누르면 QGIS 4 Dock 모드에서도 같은 localhost 브리지 기반 Kakao Viewer를 별도 브라우저 창으로 열 수 있습니다.
10. 상단 검색창에서 장소명이나 주소를 검색하고 결과를 선택하면 Kakao 지도, Roadview, QGIS가 함께 이동합니다.
11. 상단 배치 선택으로 `지도 위 / 로드뷰 아래`, `로드뷰 위 / 지도 아래`, `지도 좌 / 로드뷰 우`, `로드뷰 좌 / 지도 우`를 전환할 수 있습니다.
12. 지도와 Roadview 사이의 분할선을 드래그하면 영역 크기를 조절할 수 있고, 가운데 전환 버튼으로 두 화면의 위치를 바꿀 수 있습니다.
13. 상단의 `⛶` 버튼을 누르면 QGIS 4에서는 Dock 뷰어가 전체화면으로 전환되고, QGIS 3 외부 브라우저에서는 브라우저 전체화면으로 전환됩니다.
14. Roadview를 이동하거나 회전하면 `Kakao Roadview Position` 레이어의 레이더형 마커와 속성이 갱신됩니다.
15. 경로 영역의 출발지와 도착지 입력창에 각각 주소·장소명·좌표를 입력합니다. `현재 위치` 버튼으로 현재 Kakao 지도 중심을 넣을 수도 있습니다.
16. 좌표는 `경도,위도` 또는 `위도,경도` 형식을 지원합니다. 예: `126.9786567,37.566826` 또는 `37.566826,126.9786567`.
17. `경로 생성`을 누르고 최초 실행 시 REST API 키를 입력하면 `Kakao Mobility Route` 임시 레이어가 생성되고 전체 경로 범위로 이동합니다.
18. 좌표가 확정되면 `Kakao Route Points` 임시 레이어에 출발지는 녹색, 도착지는 빨간색 위치 핀으로 표시됩니다.
19. 경로 유형은 `추천 경로`, `최단 시간`, `최단 거리` 중에서 선택할 수 있습니다.
20. `+ 경유지`를 눌러 최대 5개까지 추가할 수 있으며, 목록 순서대로 경로에 반영됩니다. 경유지도 주소·장소명·좌표 입력과 `현재 위치` 지정을 지원합니다.
21. 출발지·경유지·도착지 입력창에 검색어를 입력하면 후보가 표시됩니다. 후보를 선택하거나 Enter로 확정하면 해당 역할의 위치 핀이 즉시 생성됩니다.
22. 경로가 생성되면 `Kakao Route Guidance` 임시 포인트 레이어와 Dock의 순서별 경로 안내 목록이 함께 생성됩니다. 안내 패널 상단에는 현재 보고 있는 경로의 출발지·경유지·도착지 개요가 표시됩니다.
23. 안내 목록의 항목을 선택하면 Kakao 지도와 Roadview가 해당 안내 지점으로 이동하고, QGIS에서도 대응하는 피처가 선택됩니다.
24. `⇅` 버튼으로 출발지와 도착지를 교환할 수 있습니다. 경유지의 `↑`, `↓` 버튼으로 이동 순서를 변경한 뒤 경로를 다시 생성할 수 있습니다.
25. `회피` 버튼을 펼쳐 유료도로, 자동차전용도로, 페리, 어린이보호구역, 유턴을 복수 선택할 수 있습니다.
26. `차량` 버튼을 펼쳐 차종 7종, 휘발유·경유·LPG 유종, 하이패스 사용 여부를 설정할 수 있습니다.
27. 경로를 한 번 이상 생성한 뒤 `플러그인 > Kakao QGIS Bridge > 경로 이력 GeoPackage 저장...`을 선택하면 현재 QGIS 세션의 검색 경로와 안내 이력을 저장할 수 있습니다.
28. 같은 GeoPackage를 다시 선택하면 이미 저장된 `history_id`는 건너뛰고 새 검색 이력만 추가합니다.
29. 저장된 두 레이어를 QGIS로 다시 불러오면 GeoPackage 내부 기본 스타일이 적용되어 경로선과 안내 SVG 심볼이 복원됩니다.
30. `경로·안내 이력 GeoJSON 내보내기...`를 선택하면 `*_routes.geojson`, `*_guidance.geojson`과 각각의 `.qml` 스타일 파일이 생성됩니다.
31. `경로·안내 이력 Shapefile 내보내기...`를 선택하면 `*_routes.shp`, `*_guidance.shp` 파일 세트와 각각의 `.qml` 스타일 파일이 생성됩니다.
32. `경로·안내 이력 GPX 내보내기...`를 선택하면 경로 이력을 GPS 교환용 `*.gpx` 파일로 저장합니다.
33. `경로 생성` 옆의 `이력` 버튼을 누르면 현재 세션의 경로 검색 이력 패널을 바로 열고 최신 이력 목록을 다시 요청합니다.
34. Dock 하단의 `이력` 탭에서 현재 세션의 경로 검색 이력을 확인하고, 항목을 선택하면 해당 경로와 안내 지점이 QGIS와 Kakao 지도에 다시 표시됩니다.
35. QGIS를 다시 실행했거나 세션 이력이 비어 있을 때 `플러그인 > Kakao QGIS Bridge > 경로 이력 불러오기...`를 선택하면 저장해 둔 GeoPackage, GeoJSON, Shapefile 이력을 다시 이력 탭으로 불러올 수 있습니다.
36. `플러그인 > Kakao QGIS Bridge > GPX 스타일 적용해서 불러오기...`를 선택하면 GPX의 `tracks`, `routes`, `waypoints` 레이어를 추가하고 같은 폴더의 QML 스타일을 자동 적용합니다.
37. 이력 항목의 `불러오기`를 선택하면 출발지·도착지·경유지와 경로 옵션을 입력창으로 다시 채웁니다.
38. 이력 항목의 `삭제`를 선택하면 현재 세션 이력에서 해당 경로와 안내 포인트를 제거합니다. 삭제한 이력이 현재 표시 중이면 QGIS의 현재 경로·안내 임시 레이어와 Kakao 지도 경로선도 함께 정리됩니다.
39. 이력 항목의 `내보내기`를 선택하면 해당 이력만 GeoPackage, GeoJSON, Shapefile, GPX 중 하나로 저장할 수 있습니다.

## 개발 메모

- Kakao 지도는 QGIS 레이어로 추가하지 않고 WebEngine 안에서만 표시합니다.
- QGIS 캔버스의 현재 목적 CRS를 기준으로 중심 좌표를 읽고, `QgsCoordinateTransform`으로 EPSG:4326 변환을 수행합니다.
- 연속 드래그 중에는 350ms 디바운스를 적용해 Kakao Roadview 요청이 과도하게 발생하지 않도록 합니다.
- Python에서 JavaScript로 값을 넘길 때는 `QWebEnginePage.runJavaScript()`를 사용합니다.
- JavaScript에서 Python으로 값을 넘길 때는 Qt의 `QWebChannel`을 사용합니다.
- Kakao 지도 또는 Roadview에서 QGIS로 이동한 직후에는 600ms 동안 정방향 재전송을 막아 순환 동기화를 방지합니다.
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
- 안내 유형은 출발·도착·경유지·직진·좌회전·우회전·유턴·회전교차로·진출입·기타로 분류해 SVG 심볼로 표시합니다.
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

## 날짜별 개발 이력

### 2026-06-24 - 기본 플러그인 구동

- Plugin Builder 없이 `metadata.txt`, `classFactory`, 메인 플러그인 클래스와 Dock Widget으로 구성된 최소 구조를 작성했습니다.
- 개발 폴더를 QGIS 플러그인 디렉터리에 심볼릭 링크로 연결하고 정상 로드를 확인했습니다.
- QGIS 메뉴·툴바 액션과 `QWebEngineView` 기반 Kakao Map·Roadview Dock을 구현했습니다.
- Kakao JavaScript API 키를 최초 입력창에서 받아 QGIS 사용자 설정에 저장하도록 변경했습니다.
- `http://localhost:8081`을 Kakao JavaScript API 기준 도메인으로 사용하는 구성을 확인했습니다.

### 2026-06-30 - 지도·로드뷰 동기화와 경로 탐색 구현

- QGIS 캔버스, Kakao Map, Roadview 사이의 양방향 중심 좌표 동기화를 확인했습니다.
- Kakao 지도 드래그와 Roadview 이동·회전에 따른 QGIS 이동을 구현했습니다.
- Kakao Local 장소·주소 검색과 검색 결과 선택 이동을 구현했습니다.
- Roadview 위치와 방향을 QGIS 레이더형 메모리 레이어로 표시했습니다.
- Kakao Mobility REST API 키 설정과 자동차 경로 탐색을 구현했습니다.
- 출발지·도착지 분리 입력, 좌표 입력, `Kakao Mobility Route` LineString 임시 레이어 생성을 확인했습니다.

### 2026-07-01 - 경로 탐색·안내 기능 완성

- 출발지·도착지 위치 핀과 경유지 추가·삭제·순서 변경, 출발지·도착지 교환을 구현했습니다.
- 경로 입력창의 장소·주소 자동 검색과 Enter 확정을 구현했습니다.
- `Kakao Route Guidance` 턴바이턴 안내 레이어와 Dock 안내 목록을 구현했습니다.
- 추천·최단 시간·최단 거리, 경로 회피, 차종·유종·하이패스 설정을 구현했습니다.
- 경로 저장 포맷은 GeoPackage 중심 구조와 SHP·KML·GeoJSON 확장 방향까지 검토했으며 저장 기능은 아직 구현하지 않았습니다.

### 2026-07-02 - 경로·안내 이력 GeoPackage 저장

- 성공한 경로 검색과 턴바이턴 안내를 세션 이력으로 누적하도록 구현했습니다.
- 경로 LineString과 안내 Point를 같은 GeoPackage의 두 레이어로 저장하고 `history_id`로 연결합니다.
- 기존 GeoPackage에 다시 저장할 때 이미 저장된 이력은 제외하고 새 이력만 추가하며 다른 레이어는 보존합니다.
- 후속 단계에서 SHP와 GPX 내보내기를 같은 이력 모델에 연결할 예정입니다.

### 2026-07-03 - 이력 심볼 복원과 GeoJSON 내보내기

- 경로선과 안내 SVG 분류 렌더러를 GeoPackage의 `layer_styles` 테이블에 기본 스타일로 저장하도록 개선했습니다.
- 안내 SVG를 Base64로 스타일에 내장해 플러그인 설치 경로와 무관하게 이동 가능한 GeoPackage로 만들었습니다.
- 저장된 GeoPackage 레이어를 QGIS에 다시 추가했을 때 경로선과 안내 심볼이 자동 복원되는 것을 확인했습니다.
- 경로와 안내 이력을 RFC 7946 GeoJSON 두 파일로 내보내고 `history_id`로 연결하도록 구현했습니다.
- 각 GeoJSON과 같은 이름의 QML 스타일을 생성해 QGIS에서 경로선과 안내 SVG 심볼이 복원되도록 했습니다.
- 경로 결과에 `guidance_count`와 `result_summary`를 추가하고 기존 GeoPackage 스키마를 자동 확장하도록 개선했습니다.
- Kakao API 키 발급과 JavaScript SDK 도메인 등록 절차를 문서화하고 `KAKAO_MAP_BASE_URL` 환경변수로 localhost 포트를 변경할 수 있게 했습니다.

### 2026-07-08 - Shapefile 이력 내보내기

- 경로와 안내 이력을 `*_routes.shp`, `*_guidance.shp` 두 Shapefile 세트로 내보낼 수 있도록 메뉴를 추가했습니다.
- Shapefile 호환성을 위해 긴 필드명을 10자 이내의 짧은 필드명으로 변환하는 별도 내보내기 레이어를 생성합니다.
- UTF-8 인코딩과 QML 스타일 파일을 함께 생성해 QGIS에서 다시 불러올 때 경로선과 안내 심볼을 쉽게 복원할 수 있게 했습니다.

### 2026-07-08 - 경로 이력 패널 MVP

- Dock의 안내 패널을 `안내`와 `이력` 탭 구조로 확장했습니다.
- 경로 생성 시 현재 세션의 검색 이력을 목록으로 갱신하고 검색 시각, 출발·도착지, 거리·시간, 안내 개수를 표시합니다.
- 이력 항목을 선택하면 해당 `history_id`의 경로와 안내 지점을 현재 QGIS 임시 레이어로 다시 표시하고 Kakao 지도 중심도 이동합니다.
- 선택한 이력을 경로 입력창으로 불러와 재검색할 수 있도록 출발지·도착지·경유지와 옵션 복원 기능을 추가했습니다.
- 선택한 이력을 현재 세션에서 삭제하고, 선택 이력만 GeoPackage·GeoJSON·Shapefile로 내보낼 수 있도록 확장했습니다.
- 저장해 둔 GeoPackage·GeoJSON·Shapefile 이력을 현재 세션 이력 탭으로 다시 불러오는 메뉴를 추가했습니다.

### 2026-07-08 - GPX 경로·트랙·경유지 내보내기

- 경로 이력을 GPS 교환용 GPX 1.1 파일로 내보내는 메뉴를 추가했습니다.
- 각 경로 이력은 `trk`와 `rte`에 함께 저장하고, 출발지·도착지·경유지·턴바이턴 안내 지점은 `wpt`로 저장합니다.
- 선택 이력 내보내기에도 GPX 형식을 추가해 개별 경로만 GPX로 저장할 수 있도록 했습니다.
- GPX 표준 요소에 담기 어려운 이력 식별자와 경로 속성은 `kakao:*` 확장 태그로 보존합니다.
- GPX와 함께 트랙·루트·웨이포인트용 QML 스타일 파일을 생성해 QGIS에서 심볼을 복원할 수 있게 했습니다.
- GPX 파일을 선택하면 `tracks`, `routes`, `waypoints` 레이어만 QGIS에 추가하고 대응 QML을 자동 적용하는 불러오기 메뉴를 추가했습니다.

### 2026-07-08 - QGIS 3.34 LTR 호환 준비

- 플러그인 메타데이터의 최소 QGIS 버전을 3.34로 조정해 QGIS 3.34 LTR 호환 점검을 시작할 수 있게 했습니다.
- QGIS 4에서도 플러그인 관리자가 호환 대상으로 인식하도록 `qgisMaximumVersion=4.99`를 명시했습니다.
- Qt5/Qt6와 QGIS 3/4 사이에서 달라질 수 있는 메시지박스 버튼, 로그 레벨, 벡터 파일 저장 액션, 스타일 DB 저장 API를 `compat.py`로 분리했습니다.
- README 설치 경로와 프로젝트 설명을 QGIS 3.34 LTR 이상 및 QGIS 4 병행 방향으로 정리했습니다.

### 2026-07-21 - QGIS 3 외부 연동과 반응형 뷰어 개선

- QGIS 3에서 Qt WebEngine 없이도 사용할 수 있도록 `external_bridge.py` 기반 외부 브라우저 연동 모드를 추가했습니다.
- 외부 Kakao Viewer와 QGIS 사이에서 지도 중심, Roadview 위치, 경로 요청, 안내·이력 이벤트를 localhost JSON API로 동기화합니다.
- QGIS 4 Dock 모드와 QGIS 3 외부 브라우저 모드가 같은 `kakao_viewer.html`을 공유하도록 정리했습니다.
- 지도·로드뷰 배치를 상하·좌우 4가지 방식으로 전환할 수 있게 했고 선택값을 브라우저 저장소에 유지합니다.
- 지도와 Roadview 사이에 분할선을 추가해 사용자가 두 화면의 높이 또는 폭을 직접 조절할 수 있게 했습니다.
- 뷰어 내부의 `⛶` 버튼으로 QGIS 4 Dock 전체화면과 QGIS 3 브라우저 전체화면을 전환할 수 있게 했습니다.
- 넓은 화면에서 뷰어가 과도하게 퍼지지 않도록 중앙 정렬과 최대 폭을 적용하고, 좁은 창에서는 자동으로 세로 배치로 접히게 했습니다.
- 창 크기 변경과 분할선 조절 후 Kakao Map/Roadview가 안정적으로 다시 배치되도록 relayout 처리와 Roadview 떨림 방지 로직을 보강했습니다.
- QGIS 3 외부 브라우저에서도 경로 생성 결과의 경로선을 Kakao 지도에 표시하도록 `path` payload와 Polyline 렌더링을 추가했습니다.
- 외부 브라우저에서 선택 이력을 입력창으로 불러오고, 이력 버튼으로 최신 이력 목록을 즉시 요청할 수 있게 했습니다.
- 선택 중인 이력을 삭제하면 안내 목록, 현재 경로선, QGIS 현재 경로·안내 임시 레이어가 함께 정리되도록 상태 동기화를 보강했습니다.
- QGIS 3 전환 안내 메시지바를 제거하고, QGIS 3/4에서 공통으로 발생하던 `Qgis is not defined` 심볼 오류를 수정했습니다.

### 2026-07-22 - 외부 브라우저 연동과 안내 패널 개선

- QGIS 4 Dock 모드에서도 하단 `외부 브라우저 연동창` 버튼으로 별도 브라우저 Kakao Viewer를 열 수 있게 했습니다.
- QGIS 4 WebChannel과 QGIS 3 외부 브리지 모두 `openExternalViewer()` 흐름을 공유하도록 연결했습니다.
- 중복된 상단 외부 브라우저 버튼을 제거하고, 하단 상태바 버튼으로 진입점을 정리했습니다.
- 안내 패널 상단에 현재 경로의 출발지·경유지·도착지 개요를 표시해 보고 있는 경로를 바로 확인할 수 있게 했습니다.
- 새 경로 생성 결과와 이력에서 불러온 경로 모두 `origin`, `waypoints`, `destination` payload를 안내 패널에 전달하도록 보강했습니다.

## 다음 확장 후보

- 이력 검색·필터와 여러 이력 비교

## 참고 문서

- QGIS Python Plugin 구조: https://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/plugins/plugins.html
- Kakao Maps JavaScript API: https://apis.map.kakao.com/web/documentation/
- Kakao API 시작하기: https://developers.kakao.com/docs/ko/tutorial/start
- Kakao 지도 Web API 가이드: https://apis.map.kakao.com/web/guide/

## License

Kakao QGIS Bridge is licensed under GPL-2.0-or-later.

Kakao Maps and Kakao Mobility APIs are third-party services governed by
Kakao's terms and policies. Users must provide and manage their own API keys.
This project does not distribute Kakao map tiles, map data, or API keys, and
is not affiliated with or endorsed by Kakao Corp.
