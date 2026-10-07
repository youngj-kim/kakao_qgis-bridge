# Windows 브리지 재시작 검증 (2026-10-07)

## 결론

현재 Windows 환경의 자동 시험에서 종료 직후 포트 재바인딩 실패는 재현되지 않았다. QGIS 3.44.14 및 4.2.2의 플러그인 종료/재생성, 1분 동시 폴링 후 즉시 재시작, 열린 연결을 유지한 종료에서도 재바인딩에 성공했다. 이 결과에 따라 독점 바인딩 및 HTTP/1.0 설정을 유지한다. 제품 코드는 변경하지 않았으며 새 ZIP은 만들지 않았다.

## 조건

- OS가 배정한 임시 포트만 사용했다. 실행 중인 사용자 QGIS, 설치 플러그인 및 8081/8082를 변경하지 않았다.
- Windows 기본 Python의 네이티브 TCP 소켓과 http.client를 사용했다. QGIS 런타임 시험은 실제 QgsApplication/캔버스와 plugin 객체를 사용했다.
- 기존 서버 구현의 SO_EXCLUSIVEADDRUSE를 그대로 적용했다. 별도 SO_REUSEADDR 설정이나 HTTP 버전 변경을 넣지 않았다.
- 카카오 SDK 호출과 사용자 API 키로 외부 네트워크 요청은 하지 않았다.

## 결과

| 시험 | 결과 |
| --- | --- |
| 아무 요청을 보내지 않은 연결을 열어 둔 상태에서 서버 종료 및 재바인딩 | 성공. 클라이언트를 닫은 뒤 재바인딩도 성공 |
| POST 본문을 일부만 보낸 연결을 유지한 종료 및 재바인딩 | 성공. 본문 전송 완료 및 연결 종료 후 재바인딩도 성공 |
| 위 두 시험의 서버 stop 소요 시간 | 각각 약 0.301초 |
| 4개 클라이언트, 400ms 간격, 60초간 state/events 폴링 | HTTP 200 응답 580건, HTTP 오류 0건, 전송 오류 0건 |
| 위 폴링을 계속하면서 서버 종료 및 새 세션으로 즉시 재시작 | 12회 모두 같은 포트에서 성공 |
| 재시작한 서버의 이전 토큰/새 토큰 | 매 회 이전 토큰 403, 새 토큰 200 |
| 종료·재시작 전환 중 폴링 | 일시적인 전송 오류 12건. 전환 구간을 포함한 HTTP 오류 0건, 성공 응답 592건 |
| QGIS 3.44.14 plugin unload → 새 plugin/브리지 생성 | 12회 모두 같은 포트에서 성공. 타이머·서버 종료 및 토큰 교체 확인 |
| QGIS 4.2.2의 같은 시험 | 12회 모두 성공 |
| 기존 회귀 검사: 동일 포트 중복 바인딩 차단 및 두 세션의 포트·토큰·이벤트 분리 | 두 검사 모두 통과 |

전환 순간의 전송 오류는 서버가 잠시 없는 동안 발생했다. 브라우저 클라이언트의 기존 재시도 정책으로 처리할 수 있는 상황이며, 포트 재바인딩 실패를 의미하지 않는다. 이번 부하 시험의 클라이언트는 HTTP 요청으로 폴링을 모사하며 실제 브라우저 JS 타이머/백그라운드 탭을 실행한 것은 아니다.

## 재실행

`tests/external_bridge_restart_stress.py`를 Windows Python으로 실행한다. 1분 시험과 재시작이 포함돼 종료까지 시간이 걸린다. 실패 원인과 성공 결과를 출력하며, 폴링 중 정상 구간의 요청 오류는 assertion으로 실패 처리한다.

`tests/qgis_bridge_restart_smoke.py`를 QGIS Python으로 각각 실행한다.

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Program Files\QGIS 3.44.14\bin\python-qgis-ltr.bat' tests/qgis_bridge_restart_smoke.py
& 'C:\Program Files\QGIS 4.2.2\bin\python-qgis.bat' tests/qgis_bridge_restart_smoke.py
```

같은 포트를 사용할 수 없으면 테스트용 임시 포트로 fallback하여 관찰 결과의 same_port에 false를 기록한다. 이번에는 모든 값이 true였다. 플러그인 unload/재생성을 검사하므로 전체 QGIS GUI 프로세스 종료·시작, 실제 브라우저의 장시간 사용, 다른 Windows 버전 및 QGIS 3.34를 검증했다고 해석하지 않는다.
