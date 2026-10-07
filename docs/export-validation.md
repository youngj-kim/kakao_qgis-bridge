# 내보내기 런타임 검증

`tests/qgis_export_smoke.py`는 QGIS Python에서 실행한다. 일반 Python에서는 QGIS 의존성 때문에 실행할 수 없다. 임시 디렉터리에 테스트 데이터를 저장하고 다시 불러오며 사용자 프로젝트나 API 키를 사용하지 않는다. Windows에서 provider가 파일을 잡고 있으면 임시 파일 삭제 오류는 테스트 결과를 가리지 않도록 무시한다.

현재 설치 환경에서 PowerShell 실행 예:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Program Files\QGIS 3.44.14\bin\python-qgis-ltr.bat' tests/qgis_export_smoke.py 'E:\Project\kakao_qgis-bridge-main'
& 'C:\Program Files\QGIS 4.2.2\bin\python-qgis.bat' tests/qgis_export_smoke.py 'E:\Project\kakao_qgis-bridge-main'
```

성공하면 각 프로세스가 `EXPORT_RESULT`에 `status: ok`와 검증 항목을 출력하고 종료 코드 0을 반환한다. 설치 버전과 저장소 경로가 다르면 해당 경로를 바꾼다.

검증 항목은 네 형식의 건수·연결·좌표계·좌표·텍스트, QML과 DB 기본 스타일 재불러오기, GPX XML·확장 속성·안내 순서, GPKG 중복 방지·추가 저장, 선택 이력의 중복 제거·다른 이력 제외, 취소 및 오류 안내다. 일반 CI는 QGIS를 설치하지 않으므로 이 스크립트는 별도 런타임 검증이다.

실제 GUI에서는 경로 두 개 이상과 안내를 만든 뒤 전체 및 선택 이력을 내보내고 스타일과 함께 다시 불러온다. 새 테스트 ZIP 설치 후 QGIS 3·4를 재시작하고 지도·로드뷰와 두 외부 연동 창의 동작도 확인한다.

## 이력 조회·가져오기·삭제 검증

같은 실행 환경에서 `tests/qgis_history_smoke.py`를 실행하면 `HISTORY_RESULT`와 `status: ok`를 출력한다. 위 명령의 스크립트 이름을 바꿔 QGIS 3·4에서 각각 실행한다.

실제 QGIS 메모리 provider와 OGR로 조회 복사본, 없는 ID, 안내·이력 정렬, GPKG/GeoJSON/SHP import와 재import 중복 방지, 필드·좌표·입력 복원, 파일 선택 취소·안내 파일 누락 오류를 확인한다. GPX는 세션 이력 import와 구분해 프로젝트에 세 스타일 레이어를 불러오는 동작을 확인한다. 삭제는 취소, 비활성·활성 이력 삭제, 전체 삭제, 안내·패널 상태 및 QAction 활성 상태를 검사한다. 확인창 응답과 뷰어는 mock을 사용하며 실제 GUI 조작 검증을 대신하지 않는다.

`tests/qgis_history_validation.py`는 WGS84/geometry·값·스키마·연결·중복·기존 ID 충돌을 실제 파일로 검사한다. 오류 후 데이터와 선택이 유지되는지, 빈 안내 GeoJSON·레거시 NULL·한 부분 MultiLineString·실제 SHP JSON 잘림이 호환되는지도 확인한다. `qgis_history_smoke.py`는 불량 파일의 UI 오류와 활성 경로 보존까지 확인한다.

## 이력 변경 실패·복구 검증

`tests/qgis_history_failure_audit.py`는 최초 결함 재현용으로 작성했으나 수정 후에는 회귀 검증으로 전환했다. 같은 QGIS 실행 명령에서 이 파일을 지정하면 `FAILURE_AUDIT`와 `status: ok`를 출력한다. 과거 기록의 `status: reproduced`와 구분한다.

실제 읽기 전용 provider에서 변경이 사전에 차단되는지, 실제 메모리 데이터에 일부 추가·삭제가 반영된 뒤 False 또는 예외가 발생했을 때 원래 geometry·속성과 선택이 복구되는지 검사한다. 성공 반환에도 데이터가 추가되지 않은 조건도 확인한다. 복구 실패에서는 잔여 데이터 공개·후속 이력 변경 차단·내보내기 허용과 활성 표시 정리를 확인한다. 정상 경로 결과의 이력 저장만 실패한 경우 경로 표시를 유지하고 실패 상태로 대기를 해제하는지도 검사한다.

## 스타일 책임 분리 검증

`tests/qgis_style_smoke.py`를 같은 QGIS 실행 명령으로 호출하면 `STYLE_RESULT`를 출력한다. 분리 전 QGIS 3.44.14·4.2.2의 실제 스타일 속성을 각각 `tests/fixtures/qgis3-styles.json`, `qgis4-styles.json`에 확보했으며 기본 실행은 해당 기준과 비교한다. `--record`는 의도적으로 새 기준을 확보할 때만 사용하며 회귀 검사에 넣지 않는다.

경로 선 속성, 안내/GPX의 분류 키·값·라벨·심볼, 핀 크기·앵커·SVG 내용, 초기 핀 범례와 category 템플릿, radar 크기·회전 필드를 비교한다. SVG base64 내용은 해시로, radar 경로는 파일명으로 비교하여 workspace 위치를 제외한다. 각 호출이 새 심볼/renderer를 반환하여 다른 호출의 객체 변경에 영향을 받지 않는지도 확인한다. 이는 실제 QGIS 객체 속성과 저장/재불러오기 검증이며 카카오 SDK의 화면 조작이나 픽셀 렌더링 비교는 아니다.

## 표시 레이어 책임 분리 검증

`tests/qgis_display_layers_smoke.py`도 같은 QGIS 실행 명령에서 호출한다. `DISPLAY_RESULT`의 status가 ok인지 확인한다. 분리 전에 확보한 `tests/fixtures/qgis3-display.json`, `qgis4-display.json`과 레이어 이름·좌표계·메모리 검사 속성·필드 순서/형식/정밀도·feature 속성/geometry·캔버스 범위를 비교한다. 기본 실행은 비교이며 `--record`는 의도적으로 새 기준을 확보할 때만 사용한다.

실제 provider와 프로젝트에서 기존 feature 갱신, 수동 feature/레이어 삭제 후 재생성, 현재 경로 교체와 레이어 수, 빈 안내 처리, 안내 선택, 프로젝트 clear 후 재생성, 반복 unload를 확인한다. 사용자의 같은 이름 레이어와 일반 GPX/사용자 레이어가 manager의 삭제 대상이 아닌지 확인한다. 내부 이력과 활성 이력의 프로젝트 전환 정책은 기존대로 유지하는지 확인하며, 프로젝트 변경 후 웹 화면/진행 중 요청의 상태 정책을 새로 적용한 테스트는 아니다. 모든 조작은 별도 offscreen 임시 프로젝트에서 수행한다.

## 가져오기 안내 그룹화 검증

`tests/qgis_import_batch_smoke.py`를 QGIS Python으로 실행한다. `IMPORT_BATCH_RESULT`의 status가 ok인지 확인한다. 여러 이력의 신규/기존 혼합, 안내 없는 경로, 파일 내부 중복, 누락 건수 복원, 기존 경로에 안내 보충, 부분 안내/고아 안내/연결 ID/안내 내용 충돌을 검사한다. 같은 검사로 수정 전 기준도 확인했다.

500개 경로·1,500개 안내와 2,000개 경로·6,000개 안내를 기존 세션에 다시 검증하는 시간을 출력한다. 이 시간에는 파일 읽기, 필드 정규화, provider 쓰기, 복구 스냅샷이 포함되지 않는다. 실행 부하에 따라 변동하므로 성능 통과 기준으로 사용하지 않는다. 파일 호환과 오류 시 보존은 기존 `qgis_history_validation.py`, `qgis_history_smoke.py`, `qgis_saved_history_audit.py`로 따로 확인한다.

## 형식 손실 및 빈 입력 안내 검증

`test_history_export.py`는 XML 1.0 금지 C0 제어문자/서로게이트/FFFE·FFFF 제거와 유효한 한글·이모지·TAB/LF/CR 보존, 문자열/속성 XML escaping, SHP의 문자/UTF-8 바이트 경계를 검사한다.

`qgis_export_smoke.py`는 실제 SHP에서 긴 한글 문자열과 경유지 JSON의 손실을 미리 집계하고 전체/선택 이력 UI에서 완료 경고와 필드별 건수 로그를 확인한다. 선택하지 않은 이력의 손실은 경고에 포함하지 않는다. SHP 및 GPX 출력 후 원래 메모리 이력 값이 그대로인지 검사하며 GPX에 제어문자가 포함된 실제 데이터를 저장하여 XML 파싱도 확인한다. 기존 네 형식 데이터/스타일과 취소·실패 검사도 유지한다.

SHP는 기존 필드별 문자 수 제한과 254바이트 호환 상한을 함께 적용하고 UTF-8 문자 경계에서 자른다. 이는 형식의 손실을 없애는 처리가 아니다. 경유지 JSON이 잘리면 다시 가져올 때 기존 경고/복원 정책을 사용한다. 전체 문자열 보존에는 GeoPackage/GeoJSON이 적합하다. GDAL의 DBF 문자열 크기와 자동 확장 설명은 [공식 드라이버 문서](https://gdal.org/en/stable/drivers/vector/shapefile.html#field-sizes)를 참고한다.

`qgis_history_smoke.py`는 빈 GeoJSON 짝 파일과 재불러오기 안내가 서로 다른지, 기존 데이터·선택·활성 경로가 보존되는지 확인한다. `qgis_history_validation.py`의 잘린 SHP JSON과 레거시 형식 호환 검사는 계속 통과해야 한다.
