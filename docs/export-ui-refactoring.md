# 내보내기 UI 컨트롤러 분리

## 범위

HistoryExportController가 전체·단일·다수 선택 이력의 형식 선택, 저장 대화상자,
덮어쓰기 확인, SHP 손실 경고, 오류 및 완료 안내를 담당한다.
HistoryExportService는 기존대로 실제 파일 출력과 스타일 저장을 담당하고,
HistoryRepository는 이력 데이터를 제공한다. 플러그인의 기존 진입점은 위임한다.

컨트롤러에 플러그인 전체를 전달하지 않는다. 명시적 콜백으로 현재 프로젝트
세대, QGIS 인터페이스와 네 형식 writer를 연결한다. 메모리 선택 레이어와
안전한 파일명 생성도 컨트롤러로 이동했다.

## 유지 및 보강

- GPKG 누적 저장·중복 제외, GeoJSON/SHP 두 레이어 및 QML, GPX 세 레이어
  스타일과 한글 속성 처리를 유지한다.
- 형식 선택창 전의 프로젝트 세대를 보관하고 선택창 직후에도 검사한다.
- GeoJSON/SHP/GPX 덮어쓰기 확인창 직후에도 세대를 검사한다.
- 선택 ID 입력이 JSON 배열이 아닌 경우 경고 후 종료한다.
- 취소와 프로젝트 전환에는 writer를 호출하거나 성공 안내를 표시하지 않는다.

## 검증과 한계

QGIS 3.44.14/4.2.2의 qgis_export_smoke.py로 실제 네 형식 파일을 작성·재개방하고,
선택 이력 격리, 중복 제거, QML, 한글, SHP 바이트 제한과 원본 보존을 확인한다.
모달 취소·전환과 writer 오류도 검사한다.
qgis_project_transition_smoke.py는 실제 project.clear/read 경계와 내보내기
대화상자 안에서의 project.clear를 검사한다.

부분 파일 출력 시 자동 롤백, 선택 내보내기의 추가 sidecar 덮어쓰기 정책,
파일 쓰기 중 비동기 취소는 이번 분리에 포함하지 않는다. 기존 정책을 유지한다.
실제 Kakao API 및 사용자의 설치 플러그인 화면 테스트는 자동 검사와 별개다.

테스트 ZIP은 dist/kakao_qgis_bridge-export-ui-test.zip이며, metadata 1.2.0 및
기존 최종 배포 ZIP은 유지한다. Git 커밋·푸시와 사용자 플러그인 설치는 수행하지 않는다.

실행 결과: 양쪽 QGIS 내보내기·프로젝트 전환·이력 smoke, Python 61개 및
JavaScript 13개 검사가 통과했다. ZIP 40개 파일이 루트 제품 파일과 바이트
일치하고 체크아웃과는 줄바꿈·끝 공백을 제외한 내용이 일치함을 확인했다.
기존 최종 ZIP 두 개의 SHA-256은 변하지 않았다.
현재 Python 런타임에는 Bandit이 없어 보안 스캔은 미실행이다.
