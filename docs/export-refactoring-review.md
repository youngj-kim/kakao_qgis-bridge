# 3단계 내보내기 분리 검토

검토일: 2026-10-07. 현재 작업 트리의 `plugin.py`, `history_export.py`, `compat.py`, 내보내기 테스트와 QGIS 스모크 스크립트를 정적으로 확인했다. 이번 단계에서는 실행 코드와 배포 ZIP을 변경하지 않는다. 사용자가 확인한 QGIS 3·4 동시 실행의 정상 작동과 충돌 해결을 기존 동작 기준으로 유지한다.

## 결론

내보내기 분리를 진행하는 것이 적절하다. 다만 형식별 메서드를 이동하는 것만으로 끝내면 UI, 이력 검색, 스타일 생성에 대한 플러그인 의존이 그대로 남는다. 먼저 현재 파일 출력의 기준을 확보하고, 파일 쓰기·형식 변환·출력 스타일 저장을 `HistoryExportService`로 옮긴다. 파일 선택·덮어쓰기 확인·이력 선택·성공 및 오류 표시는 플러그인에 남긴다.

## 현재 구조와 보존할 계약

| 영역 | 현재 진입점 또는 구현 | 보존할 동작 |
| --- | --- | --- |
| 단일·다중 선택 | `_export_single_route_history`, `_export_selected_route_histories`, `_export_route_histories` | 중복 선택 제거, 선택 이력에 해당하는 경로·안내만 출력 |
| 전체 이력 | `_save_route_history_geopackage`, `_export_route_history_geojson`, `_export_route_history_shapefile`, `_export_route_history_gpx` | 기존 메뉴와 저장 대화상자, 저장 건수 안내 |
| GeoPackage | `_write_history_layer`, `_existing_history_ids`, `_history_layer_subset` | 기존 history_id를 제외하고 추가, 부족한 필드 추가, 기존 다른 레이어 유지, DB 기본 스타일 저장 |
| GeoJSON | `_write_geojson_history_layer`, `_paired_output_paths` | routes/guidance 두 파일, RFC7946 및 좌표 정밀도 옵션, UTF-8, 각 QML |
| Shapefile | `_write_shapefile_history_layer`, `_shapefile_compatible_layer`, 필드 매핑 | 짧은 필드명과 기존 길이 제한, 좌표계, 한글 속성, 두 파일과 부속 파일·QML |
| GPX | `_write_gpx_history`, `_append_gpx_*`, `_save_gpx_sidecar_styles` | trk/rte/wpt 구성, Kakao 확장 속성, 안내 순서, tracks/routes/waypoints QML |

`history_export.py`는 현재 XML 이스케이프·문서 작성만 담당한다. 기존 테스트도 이스케이프 한 건이며 실제 파일 쓰기, 필드, 스타일, 재불러오기를 검증하지 않는다. 기존 QGIS 런타임 스모크는 레이어 생성과 브리지를 확인하지만 내보내기 형식 전체의 검증을 대신하지 않는다.

## 분리 경계

### HistoryExportService

- 경로·안내 레이어와 출력 경로, 형식, 명시적인 QGIS transformContext를 입력으로 받는다. 플러그인 객체나 iface는 받지 않는다.
- 출력 파일명 계산, SHP 필드 변환, GPX 문서 구성, GPKG 추가 저장과 스타일 저장을 맡는다.
- 결과는 경로 건수, 안내 건수, 출력 경로 목록으로 반환한다. GPKG 건수는 전체 건수가 아니라 새로 저장한 건수라는 현재 의미를 유지한다.
- 실패는 오류 정보로 호출자에게 전달하고 서비스에서 대화상자를 열거나 메시지바를 호출하지 않는다.
- `compat.py`의 QGIS 3·4 writer enum 및 DB 스타일 저장 호환 처리를 계속 사용한다.

### 스타일 의존성

GeoJSON·SHP·GPKG는 전달받은 레이어의 renderer를 복제해 저장한다. GPX는 `_route_line_symbol`, `_route_pin_symbol`, `_guidance_symbol`에 의존한다. 이 세 생성 기능은 내보내기 전용이 아니므로 통째로 서비스에 복제하지 않는다. 첫 분리에서는 선 심볼과 GPX waypoint renderer를 명시적으로 전달하고 서비스에서 clone해 사용한다. 전체 StyleFactory와 LayerManager 분리는 후속 단계로 둔다.

### 플러그인에 남길 책임

선택 이력 조회와 대상 레이어 준비, 기본 파일명·저장 대화상자, 덮어쓰기 확인, 성공·실패 안내, QAction과 뷰어 신호 연결은 유지한다. 필요하면 기존 private writer 메서드는 잠시 서비스 호출 래퍼로 남겨 호출부 변경을 제한한다. 래퍼에 파일 쓰기 구현을 중복 보관하지 않는다.

공유 함수 `_route_points_from_geometry`, `_safe_number`, `_safe_float`는 뷰어·이력 복원에서도 사용한다. 호출 관계를 확인한 뒤 작은 공통 유틸리티로 이동하거나 현 위치를 유지한다. 서비스가 플러그인의 private 함수에 역으로 의존하지 않도록 한다. SHP 내보내기 매핑과 불러오기 매핑은 기존 대응 관계를 테스트로 확인하고 스키마 전체 통합은 후속 변경으로 둔다.

## 분리 전에 고정할 주의점

- GPX의 완료 안내 건수는 연결된 안내 feature 수다. 실제 wpt에는 출발·도착·경유지도 포함되며 잘못된 좌표의 안내는 생략될 수 있다. 단순 wpt 개수와 안내 건수를 같다고 검증하지 않는다.
- `_route_points_from_geometry`는 multipart의 첫 부분만 사용한다. 기존 동작을 기록하고 구조 분리와 함께 multipart 지원을 추가하지 않는다.
- GPX 전체 내보내기의 확인은 현재 `.gpx`만 대상으로 하며 QML은 별도 확인 없이 쓰인다. 선택 내보내기도 전체 내보내기와 동일한 사전 파일 목록 확인을 거치지 않는다. 이 차이는 후속 동작 개선 대상으로 남긴다.
- 경로와 안내, 데이터와 스타일은 순차 저장된다. 후속 저장 실패 시 앞선 파일이 남을 수 있고 GPKG 저장도 두 레이어를 하나의 트랜잭션으로 묶지 않는다. 서비스 분리만으로 원자성을 보장한다고 설명하지 않는다.
- SHP 문자열 길이 제한과 GPX 안내 좌표 생략은 기존 형식 정책이다. 이 단계에서 저장 스키마·길이·좌표 처리 정책을 바꾸지 않는다.

## 권장 진행 순서와 완료 기준

1. **기존 출력 기준 확보:** 두 경로와 안내, 경유지, 한글·XML 특수문자가 포함된 이력으로 QGIS 3·4에서 네 형식의 파일을 만들고 다시 연다. 현재 코드로 먼저 통과시켜 구조 변경 전부터 있는 문제와 회귀를 구분한다.
2. **파일 쓰기 서비스 분리:** GeoJSON·SHP, GPX, GPKG 순서로 이동한다. 형식별 출력 계약과 스타일 의존성을 유지하고 각 단계에서 기준 검증을 반복한다.
3. **호출부 정리:** 단일·다중 선택과 전체 이력이 같은 서비스를 사용하도록 연결한다. UI 취소 시 파일을 쓰지 않고 오류 시 기존 실패 안내로 돌아오는지 확인한다.
4. **수동 확인과 패키지:** QGIS 3·4에서 메뉴·선택 이력 내보내기와 스타일 재불러오기를 확인한 뒤 테스트 ZIP을 만든다. 지도·로드뷰·동시 외부 연동은 최종 회귀 확인에 포함한다.

파일 검증에서는 geometry·CRS·history_id 연결·안내 순서·속성·필드명을 비교한다. GPX 생성 시각 등 가변 값은 제외한다. GPKG는 같은 이력을 두 번 저장해 중복이 늘지 않는지, 이후 새 이력은 추가되는지 확인한다. SHP의 짧은 필드명을 사용하는 QML, GPX의 세 QML, GPKG의 DB 기본 스타일을 실제 로드해 renderer와 심볼 경로를 확인한다. QGIS 버전별 결과는 별도로 남긴다.

이번 검토만으로 내보내기 런타임 검증이 완료된 것은 아니다. 다음 구현 단계의 첫 작업은 기존 출력 기준 확보다.
