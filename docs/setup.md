# 설치와 API 키 설정

[English setup and usage guide](guide.en.md)

QGIS 플러그인 관리자의 **ZIP에서 설치**로 설치하고 QGIS를 다시 시작한 뒤 Kakao QGIS Bridge를 활성화합니다. 기존 외부 브라우저 탭은 닫고 플러그인 버튼으로 새 창을 여세요.

## Kakao API 키 설정

### 키 발급 및 앱 등록

1. [Kakao Developers](https://developers.kakao.com/)에 카카오 계정으로 로그인하고 개발자 등록을 완료합니다.
2. 앱 관리 화면의 전체 앱 목록에서 `앱 생성`을 선택하고 앱 이름, 회사·단체명, 카테고리와 서비스 또는 프로젝트를 나타내는 대표 도메인을 입력합니다.
3. 생성한 앱에서 `앱 > 플랫폼 키`로 이동합니다. 앱 생성 시 JavaScript 키와 REST API 키가 함께 생성됩니다.
4. `JavaScript 키`를 선택하고 `JavaScript SDK 도메인`에 `http://localhost:8081`과 `http://localhost:8082`를 모두 등록합니다. 외부 브리지의 대체 포트와 QGIS 동시 실행에 필요합니다.
5. 플랫폼 키 화면의 JavaScript 키는 Kakao Map·Roadview·Local 검색에, REST API 키는 Kakao Mobility 경로 탐색에 사용합니다.
6. 플러그인 최초 실행 입력창에 JavaScript 키를 입력하고, 최초 경로 생성 입력창에는 REST API 키를 입력합니다.

이 플러그인은 어드민 키를 사용하지 않습니다. 어드민 키는 권한이 크므로 플러그인에 입력하거나 저장소에 커밋하지 마세요. 자세한 최신 절차는 [Kakao API 시작하기](https://developers.kakao.com/docs/ko/tutorial/start)와 [Kakao 지도 Web API 가이드](https://apis.map.kakao.com/web/guide/)를 참고하세요.

### 8081과 8082를 모두 등록하는 이유

플러그인의 외부 브라우저 뷰어는 QGIS와 통신하는 로컬 서버를 사용합니다. 이 서버는 **8081을 먼저 사용하고, 이미 사용 중이면 8082로 전환**합니다.

- `http://localhost:8081`: 기본 연결 주소입니다.
- `http://localhost:8082`: 8081을 다른 QGIS나 프로그램이 사용 중일 때 사용하는 대체 주소입니다. 예를 들어 QGIS 3과 QGIS 4에서 외부 연동을 동시에 열면 먼저 시작한 서버가 8081, 다음 서버가 8082를 사용할 수 있습니다.

Kakao JavaScript SDK는 등록한 출처에서만 해당 키를 사용할 수 있습니다. **포트가 다르면 서로 다른 출처**이므로 8081만 등록하면 8082로 연결될 때 지도가 로드되지 않을 수 있습니다. 두 주소를 같은 JavaScript 키에 미리 등록하면 자동 포트 전환과 동시 실행을 지원할 수 있습니다. 새 키를 발급받을 필요는 없습니다.

두 주소 등록은 SDK 사용을 허용하는 설정입니다. 두 포트가 모두 사용 중인 상황까지 해결하는 것은 아니며, 이 경우 플러그인이 안내를 표시합니다.

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

내장 WebEngine의 기준 URL을 변경하려면 Windows 사용자 환경변수 `KAKAO_MAP_BASE_URL`을 설정합니다. 이 설정은 외부 브리지의 8081/8082 포트를 변경하지 않습니다. 예를 들어 내장 기준 URL을 9000번 포트로 바꾸려면 다음과 같이 설정합니다.

```powershell
[Environment]::SetEnvironmentVariable("KAKAO_MAP_BASE_URL", "http://localhost:9000/kakao_qgis_bridge/", "User")
```

그다음 Kakao Developers의 `앱 > 플랫폼 키 > JavaScript 키 > JavaScript SDK 도메인`에도 경로를 제외한 다음 출처를 등록합니다.

```text
http://localhost:9000
```

환경변수의 프로토콜·호스트·포트와 Kakao Developers 등록값이 일치해야 합니다. 변경 후에는 QGIS를 완전히 종료했다가 다시 실행하세요. 환경변수를 삭제하면 기본값인 8081번 포트로 돌아갑니다.


## QGIS 3 외부 브라우저 연동 모드

Qt WebEngine/WebChannel을 사용할 수 있는 환경에서는 Dock 내부의 Kakao Map/Roadview를 사용합니다. 해당 모듈을 불러올 수 없으면 외부 브라우저 모드를 사용하며, 실제 실패 원인은 Dock 안내에 표시됩니다.

QGIS 3에서는 외부 브라우저 연동 모드로 사용할 수 있습니다. 플러그인이 기본 포트 8081에 로컬 브리지 서버를 띄우고, 이미 사용 중이면 8082로 연결합니다. `외부 연동 창 열기` 버튼은 실제 연결된 포트의 Kakao Viewer를 기본 브라우저에서 엽니다. QGIS 3·4의 외부 연동을 동시에 사용할 수 있으며, 먼저 실행한 서버가 8081을 사용합니다. 두 포트가 모두 사용 중이면 안내를 표시합니다.

외부 브라우저 연동 모드에서도 QGIS 캔버스 중심 좌표는 EPSG:4326으로 변환되어 브라우저 Kakao Map/Roadview로 전달됩니다. 브라우저의 Kakao 지도나 Roadview 위치 이동도 localhost API를 통해 QGIS 캔버스와 Roadview 위치 레이어로 다시 전달됩니다. 단, Dock 내부 렌더링은 사용하지 않으므로 브라우저 창은 QGIS와 별도로 관리됩니다.

Kakao Developers의 `[플랫폼 키] > [JavaScript 키] > [JavaScript SDK 도메인]`에 아래 두 값을 등록해야 합니다. 기존 키를 그대로 사용할 수 있습니다. `제품 링크 관리 > 웹 도메인` 등록과는 별도 설정입니다.

```text
http://localhost:8081
http://localhost:8082
```

외부 브리지 포트는 자동 선택되며, `KAKAO_MAP_BASE_URL`은 내장 뷰어의 기준 URL 설정입니다. 새 패키지 설치 후 두 QGIS를 다시 시작하고 기존 외부 탭을 닫은 뒤 플러그인 버튼으로 새 창을 여세요.
