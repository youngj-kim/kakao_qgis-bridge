# Kakao QGIS Bridge 1.2.0

## 설치와 키 설정

1. QGIS 플러그인 관리자에서 배포 ZIP을 설치하고 QGIS를 다시 시작한다.
2. Kakao Developers의 앱에서 JavaScript 키와 REST API 키를 확인한다.
3. JavaScript 키의 JavaScript SDK 도메인에 아래 두 출처를 등록한다.

   - `http://localhost:8081`
   - `http://localhost:8082`

4. `Kakao Map / Roadview`를 열어 JavaScript 키를 입력한다. 최초 경로 생성 시 REST API 키를 입력한다. 변경은 플러그인의 각 API 키 설정 메뉴에서 한다.

JavaScript 키는 지도·로드뷰·장소 검색, REST API 키는 Mobility 경로 탐색에 사용한다. 키에는 공백이나 전각 문자를 넣지 않는다. 키 입력값은 QGIS 사용자 설정에 저장되며 암호화되지 않는다. 실제 키를 소스나 배포 파일에 넣지 않는다.

공식 도메인 설정 안내: https://apis.map.kakao.com/web/guide/

## 외부 브라우저와 동시 실행

WebEngine/WebChannel을 사용할 수 없으면 외부 브라우저 연동을 사용한다. 내장 뷰어에서도 외부 창을 열 수 있다. 플러그인 버튼으로 새 창을 연다. 외부 서버는 8081을 먼저 사용하고 사용 중이면 8082를 사용한다. 두 포트가 모두 사용 중이면 오류를 안내한다. QGIS 3·4를 동시에 사용할 때도 두 도메인을 등록한다.

오래된 탭은 이전 세션 토큰 때문에 403이 날 수 있다. 현재 QGIS의 버튼으로 다시 연다. 주소를 직접 입력하면 인증되지 않는다. 도메인 미등록에 따른 SDK 오류와 로컬 브리지의 403은 원인이 다르다.

`KAKAO_MAP_BASE_URL`은 내장 WebEngine의 기준 URL 설정이며 외부 서버 포트를 바꾸지 않는다. 내장 기준 URL을 바꾼 경우 그 출처도 SDK 도메인에 등록한다.

## 검증 범위와 제한

- 실제 자동 실행 검증: Windows QGIS 3.44.14 / 4.2.2. 최소 선언 3.34는 이번 버전에서 실행 미검증이다.
- 동기화 대상은 중심 좌표다. 줌·축척은 동기화하지 않는다.
- 경로 이력은 메모리에서 관리한다. 종료 전에 GeoPackage 또는 GeoJSON으로 저장한다. 자동 저장은 지원하지 않는다.
- SHP는 긴 문자열·경유지 JSON을 잘라낼 수 있으며 손실이 있으면 경고한다. 완전한 속성 보존은 GeoPackage/GeoJSON을 사용한다.
- 외부 브라우저 토큰은 URL에 포함된다. REST 키의 인증 관리자 저장은 후속 개선 사항이다.
- SDK 임베드의 약관·쿼터 적합성은 별도 확인 대상이다.

소스, 전체 변경 기록과 검증 문서: https://github.com/youngj-kim/kakao_qgis-bridge
