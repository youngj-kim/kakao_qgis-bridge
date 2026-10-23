# Kakao QGIS Bridge

QGIS와 Kakao Map·Roadview의 위치와 확대 수준을 연동합니다. Qt WebEngine/WebChannel이 있으면 도크 안에서, 없으면 외부 브라우저에서 실행합니다.

**현재 버전: 1.3** · [1.3 릴리즈 노트](CHANGELOG.md#13--2026-10-23) · [사용 가이드](docs/usage.md)

## 설치와 시작

1. 배포 ZIP을 QGIS의 **플러그인 관리 및 설치 → ZIP에서 설치**로 설치합니다.
2. QGIS를 다시 시작하고 **Kakao QGIS Bridge**를 활성화합니다.
3. Kakao JavaScript 키의 SDK 도메인에 `http://localhost:8081`과 `http://localhost:8082`를 등록합니다.
4. **Kakao Map / Roadview**를 열어 JavaScript 키를 입력합니다. 자동차 경로를 처음 생성할 때 REST API 키를 입력합니다.

각 사용자가 자신의 API 키를 등록합니다. 키 변경·환경변수·포트와 외부 연동은 [설치와 API 키 설정](docs/setup.md)을 참고하세요.

## 주요 기능

- QGIS↔Kakao Map 이동·확대·축소 동기화와 Roadview 위치·방향 표시
- 장소·주소 검색, 지도 종류 및 Roadview 도로 표시 전환
- 자동차 경로, 최대 5개 경유지, 회피·차량 설정과 순서별 안내
- 경로 이력 불러오기 및 GeoPackage·GeoJSON·Shapefile·GPX 내보내기
- 카카오·네이버 GPKG 경로의 거리·시간·통행료·예상 택시요금 비교
- 압축된 탐색창, 상하·좌우 배치, 전체화면과 **EN / KR** 언어 전환

## 지원 환경과 확인 범위

선언된 지원 범위는 QGIS 3.34 이상 및 QGIS 4 / Qt 6입니다. QGIS 3.34는 아직 실행 검증하지 않았습니다.

2026-10-23 사용자가 QGIS 3.44 기능 확인과 QGIS 4 기존 기능 재확인을 완료했습니다. 개발 중 런타임 검사 환경은 Windows QGIS 3.44.14 / 4.2.2입니다. 모든 운영체제와 조합의 검증을 의미하지는 않습니다.

## 사용 시 알아둘 점

경로 이력은 자동 저장되지 않습니다. 종료 전에 내보내세요. 완전한 속성 보존에는 GeoPackage 또는 GeoJSON을 사용합니다. Shapefile은 긴 문자열과 경유지 정보가 잘릴 수 있습니다.

확대 수준은 카카오의 이산 단계에 맞춰져 QGIS 축척과 정확히 일치하지 않을 수 있습니다. 줌만 할 때 Roadview 촬영 위치는 유지합니다. 언어 전환은 뷰어의 주요 조작부에 적용되며 SDK 지도 지명, QGIS 메뉴·대화상자 및 일부 상태 메시지는 전환 대상이 아닙니다.

API 키는 QGIS 설정에 암호화 없이 저장됩니다. 외부 연동의 세션 토큰은 URL에 포함됩니다. 지도는 QGIS XYZ/TMS 레이어로 등록하지 않습니다.

## 문서

- [사용 가이드](docs/usage.md) · [설치와 API 키 설정](docs/setup.md)
- [릴리즈 노트와 변경 기록](CHANGELOG.md) · [배포 체크리스트](docs/release-checklist.md)
- [개발 구조와 테스트](docs/development.md)
- [경로 비교](docs/route-comparison.md) · [요금 비교](docs/fare-comparison.md)
- [과거 개발·검토 기록](docs/archive/README.md)

## 라이선스

[GPL-2.0-or-later](LICENSE). Kakao 지도·Mobility API에는 제공처의 이용 조건과 쿼터가 적용됩니다. 이 프로젝트는 Kakao의 공식 제품이 아니며 API 키와 지도 타일을 배포하지 않습니다.
