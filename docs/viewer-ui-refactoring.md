# Viewer UI JavaScript 분리

## 진행 순서와 경계

1. viewer_search.js: Local 장소·주소 검색, 결과 정규화·중복 제거, 결과 DOM,
   폼/지우기/키보드 이벤트와 요청 세대 취소. 검색 분리 후 기존 및 신규 검사를 실행했다.
2. viewer_guidance.js: 안내 목록·요약·출발/경유/도착 개요, 안내 선택,
   SDK 경로선 생성·교체·정리와 API 준비 전 payload 보관. 추가 검사 후 다음 단계로 진행했다.
3. viewer_history.js: 이력 목록·활성 이력·내보낼 선택 ID, 전체 선택/해제,
   불러오기·삭제·내보내기 브리지 호출. 추가 검사와 전체 화면 조립 검사로 검증했다.

각 모듈은 factory에서 DOM 노드와 명시적 콜백을 받는다. map/bridge 참조는
getter로 받아 늦은 SDK/WebChannel 초기화를 처리하고, 자체 상태는 클로저에
보관한다. 기존 브리지 시그널/함수명, window.centerKakaoMap과
window.loadRouteHistoryInput 진입점 및 기존 레이아웃은 유지한다.

HTML에는 세 모듈 marker를 둔다. viewer_page.load_viewer_template가 패키지의
JavaScript를 inline으로 조립하며 도크와 외부 서버가 동일한 함수를 사용한다.
외부 서버의 신규 정적 파일 endpoint, 인증 우회, 추가 네트워크 요청은 없다.
기존 SDK 키·외부 브리지 토큰 삽입과 WebChannel 교체는 각 호출 경로에서 유지한다.
CI는 모듈이 포함된 JavaScript 구문 검사와 모든 신규 JS 테스트를 실행하도록 갱신했다.

## 보강한 동작

- 검색을 취소·대체한 후 늦은 SDK 응답은 무시한다. 취소 때 주 검색 버튼도
  서비스 준비 상태에 맞게 복구해 비활성 상태가 남지 않도록 한다.
- JSON 파싱 실패 시 안내/이력 컨트롤러에 빈 데이터를 전달해 기존 DOM도 정리한다.
- 이력 payload가 null이면 빈 목록으로 처리한다.

## 검증

Python 62개, JavaScript 28개, 조립된 네 inline 스크립트와 외부 브리지의 구문
검사 및 Python 컴파일이 통과했다. JS 28개 중 기존 13개, 신규 15개다.
신규 JS 검사는 SDK·DOM fixture를 사용하고 실제 Kakao API를 호출하지 않는다.
전체 페이지 검사는 도크 및 외부 연결의 조립된 제품 스크립트를 함께 실행해
브리지 시그널, 탭 전환, 프로젝트 reset 중복 방지와 잘못된 payload 처리를 검사한다.

qgis_viewer_page_smoke는 실제 도크 _load_viewer와 외부 서버 _viewer_html 경로를
QGIS 3.44.14/4.2.2에서 실행해 모듈 순서와 키·토큰·WebChannel 계약을 확인한다.
실제 WebEngine은 의도적으로 비활성화해 사용자 키/네트워크를 사용하지 않는다.
브리지 런타임·프로젝트 전환·이력·네 형식 내보내기의 QGIS 회귀도 확인한다.

## 남은 범위

경로 입력/경유지 편집과 요청 실행, SDK 초기화·지도/로드뷰 동기화·레이아웃은
아직 HTML 메인 스크립트에 남는다. 안내 UI 분리를 경로 기능 전체 분리로
표현하지 않는다. 다음 구조 개선 후보는 경로 입력 컨트롤러다.
실제 설치 화면과 Kakao SDK 지도·로드뷰의 수동 테스트는 별도이며,
Bandit은 현재 Python 환경에 없어 이번 단계의 보안 스캔은 미실행이다.

누적 테스트 ZIP은 dist/kakao_qgis_bridge-viewer-ui-test.zip이다.
metadata 1.2.0과 기존 최종 ZIP은 유지한다. 사용자 설치, Git 커밋·푸시,
release/tag 생성은 이번 단계에서 수행하지 않는다.

최종 결과: 위 QGIS 회귀는 양쪽 런타임에서 모두 통과했다. ZIP 44개 파일의
무결성·루트 제품 파일 바이트 일치·체크아웃 텍스트 일치·키 설정/캐시 제외를
확인했고 기존 최종 ZIP 두 개의 SHA-256은 유지했다.
