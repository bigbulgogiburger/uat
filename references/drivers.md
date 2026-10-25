# 드라이버 — Android(adb) · 웹(브라우저 MCP) · API 러너 · 진단 빌드

레인이 화면과 API 를 "사람처럼" 다루는 도구와 그 함정이다. 함정 대부분은 시간을 잃는 종류다. 결함으로 잘못 적히는 함정도 있다.

## 목차
1. Android — ui.py
   1.1 찾기와 보기: dump 와 shot
   1.2 입력
   1.3 키보드 앱(IME)
   1.4 클립보드 헬퍼(ClipSet) 빌드
   1.5 네트워크 · 앱 제어 · 로그
   1.6 파일(사진·첨부) 준비
   1.7 기기 설정과 원복
2. 웹 — 브라우저 자동화 MCP
3. API — api.py
4. 진단 빌드 — 진짜 오류 문자열을 손에 넣기
5. 셸 함정

---

## 1. Android — `scripts/android/ui.py`

### 1.1 찾기와 보기: dump 와 shot

- **먼저 `dump` 로 찾는다.** 요소의 문구·좌표·플래그(C 클릭 · S 스크롤 · F 포커스 · ✓ 선택 · x 비활성)가 나온다. 탭할 대상은 `tap "<문구>"` 로 찾는다. 짧은 라벨은 정확히 그 문구인 요소를 우선한다. 같은 문구가 여럿이면 `--nth`.
- **볼 때는 `shot`.** dump 에 있다는 것과 사람 눈에 보인다는 것은 다르다. 흰 배경에 흰 글씨, 다른 레이어에 가려진 버튼, 화면 밖으로 밀린 CTA 는 전부 dump 에 있었다. 시각 판정(대비·잘림·겹침·배치·로딩 끝)은 `shot <TC-설명>` 후 `.s.png`(축소본)를 Read 로 연다.
- 웹뷰·캔버스·커스텀 렌더러 안의 요소는 dump 에 안 나올 수 있다. 이때는 shot 으로 좌표를 잡아 `tapxy` 를 쓴다. "dump 에 없다"를 "화면에 없다"로 판정하지 않는다.
- 목록이 길면 `swipe up` 으로 아래를 본 뒤 다시 dump 한다. "없다" F 는 끝까지 스크롤한 다음에만 준다.

### 1.2 입력

- `type "<텍스트>"` 는 포커스된 칸에 입력한다. 먼저 칸을 `tap` 해서 포커스를 준다(dump 의 F 플래그로 확인).
- ASCII 는 키 입력으로, 그 외(한글 등)는 클립보드 붙여넣기로 들어간다. `adb shell input text` 는 비 ASCII 를 넣지 못한다.
- 비밀 값은 `secret_type.py <별칭> <KEY>` 로 넣는다(값 비출력). 숫자 칸은 `--digits` 로 숫자만 보낸다.
- `clear [N]` 은 포커스 칸을 비운다. 자동 서식(하이픈 삽입 등)이 있는 칸은 비운 뒤 dump 로 빈 것을 확인한다.

### 1.3 키보드 앱(IME)

에뮬레이터를 재기동하면 기본 키보드 앱이 다시 켜질 수 있다. 증상은 셋이다. 붙여넣기 메뉴가 입력칸을 가리고, 마이크 권한 팝업이 반복되고, 키보드가 화면 아래 절반을 덮어 dump 좌표가 어긋난다.
- 측정 동안 끄고 진행해도 된다: `adb shell ime list -s` 로 이름을 보고 `adb shell ime disable <id>`.
- 끈 사실을 `work/driver-notes.md` 에 적고, **회차 정리 때 `ime enable <id>` · `ime set <id>` 로 되돌린다.**

### 1.4 클립보드 헬퍼(ClipSet) 빌드

비 ASCII 입력은 기기 클립보드에 텍스트를 넣은 뒤 붙여넣는다. 셸 권한으로 클립보드를 설정하는 작은 dex 가 필요하다(`scripts/android/ClipSet.java`).

```bash
javac --release 8 -cp <sdk>/platforms/android-<N>/android.jar ClipSet.java
<sdk>/build-tools/<ver>/d8 --output . ClipSet.class          # → classes.dex
adb push classes.dex /data/local/tmp/uat-clip.dex             # 프로필 android.clip_dex 와 같은 경로
```

ui.py 는 `CLASSPATH=<clip_dex> app_process /system/bin ClipSet <base64>` 로 부른다. 텍스트는 Base64 로 넘어가므로 셸 따옴표 문제가 없다. 기기를 초기화하면 다시 push 한다.

### 1.5 네트워크 · 앱 제어 · 로그

- `net off|on`: 비행기 모드로 끊고 잇는다. **끝나면 반드시 on.** 레인 끝 상태에 "네트워크 on"을 넣는다. 오프라인 TC 뒤에 on 을 잊으면 다음 레인 전체가 "연결 실패" 결함을 쏟아낸다.
- 「서버 장애」와 「기기 오프라인」은 다른 시험이다. 앱 → 서버 연결 실패는 기기 네트워크로 재현한다. 서버를 내리는 것은 서버 측 장애(위임 서버 다운 등)를 요구하는 TC 에서만 한다(가이드 예외 규칙).
- `app start|stop|restart|clear`: clear 는 앱 데이터 삭제다(로그아웃 + 첫 실행). 로그인 상태를 지우므로 레인 끝 상태로 되돌리는 비용이 크다. 필요할 때만 쓴다.
- `log [--tags …]`: 앱·런타임 오류 로그. 크래시·예외는 F 의 증거로 첫 줄을 남긴다(비밀이 섞여 있으면 마스킹된다).
- `deeplink <URI>`: 알림·외부 링크 진입 TC 에 쓴다.

### 1.6 파일(사진·첨부) 준비

- 갤러리에 테스트 사진을 미리 넣어 둔다(`/sdcard/Pictures/UAT/`). push 뒤에는 미디어 스캔을 해야 갤러리에 보인다:
  `adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Pictures/UAT/<파일>`
- 크기 초과·비허용 형식 같은 경계 파일은 `RUN/work/` 에 만들어 push 한다. 실제 사람 사진·문서를 쓰지 않는다.

### 1.7 기기 설정과 원복

글자 크기(`settings put system font_scale`), 회전, 다크 모드, 키보드 앱, 네트워크를 바꾸는 TC 가 있다. 바꾼 레인이 되돌리고, 못 되돌렸으면 end_state 에 적는다. 회차 정리 때 메인이 한 번 더 확인한다.

## 2. 웹 — 브라우저 자동화 MCP

세션에 연결된 브라우저 자동화 MCP(Chrome DevTools · Playwright · 브라우저 확장 등) 중 하나를 쓴다. 레인 가이드 §1 에 어느 것을 쓰는지 적는다.

- **레인 전용 탭/컨텍스트**를 열고 끝나면 닫는다. 사람이 쓰는 탭은 건드리지 않는다. 컨텍스트를 나눌 수 있으면 `ui_parallel` 을 올려 UI 레인을 병렬로 돌린다(계정도 나눈다).
- 요소는 접근성 스냅샷으로 찾는다. 시각 판정은 스크린샷 파일을 `RUN/shots/` 에 저장해 Read 로 연다.
- **콘솔 오류와 실패한 네트워크 요청도 증거다.** 화면이 멀쩡해 보여도 4xx/5xx·JS 예외가 있으면 기록한다. 캐시가 있을 때만 나는 오류는 같은 동작을 두 번 해야 보인다.
- 브라우저의 알림창(alert/confirm)은 자동화를 멈춘다. 그런 버튼은 피하거나, 대화상자 처리 도구로 바로 닫는다.
- 로그인 비밀번호 입력도 비밀 규칙을 따른다. 값을 프롬프트·스크립트에 쓰지 않는다. 별도 입력 헬퍼가 없으면 사람이 로그인한 세션을 레인이 이어받는 방식을 쓴다.

## 3. API — `scripts/api.py`

```bash
python $S/api.py --as acct2 GET /orders/{{acct1.ORDER_ID}}
python $S/api.py --as acct2 -H 'X-Forwarded-For: 203.0.113.21' POST /auth/sms/send '{"phone":"{{acct2.PHONE}}"}'
python $S/api.py login acct2 --fresh · refresh acct2 · forget acct2
```

- `{{별칭.KEY}}` 는 경로·본문·헤더 어디서든 실제 값으로 바뀌고, 출력에서는 다시 `<별칭.KEY>` 로 가려진다. 값의 출처는 비밀 파일과 토큰 캐시(ACCESS·REFRESH·REFRESH_PREV)다.
- `--as` 를 주면 프로필 `api.auth_header` 를 붙인다. 캐시가 없거나 TTL 이 지났으면 프로필 `api.login` 시퀀스로 먼저 로그인한다.
- 토큰 회전 TC: `refresh` 하면 이전 refresh 가 `REFRESH_PREV` 로 남는다. `{{acct2.REFRESH_PREV}}` 로 재사용 감지를 잰다. 이런 TC 는 API 전용 계정으로만 한다.
- 응답의 요지(상태코드·오류 code·핵심 필드)를 evidence 에 적는다. 전체 바디를 붙이지 않는다.
- `--headers` 는 보안 헤더 등 일부 응답 헤더를 보여 준다.

## 4. 진단 빌드 — 진짜 오류 문자열을 손에 넣기

증상(화면 문구)만으로 원인을 단정하면 오래 헤맨다. 예를 들어 "네트워크 연결을 확인해 주세요"는 모든 실패에 같은 문구를 쓰는 앱에서는 아무 정보도 주지 않는다. 실제 사례에서 사내망 TLS 인터셉트를 원인으로 단정하고 오래 헤맸는데, 실제 원인은 임베드 HTML 의 스크립트 순서였다.

1. 로그로 먼저 본다(`ui.py log --tags …`, 서버 로그, 브라우저 콘솔). 실제 오류 코드·문자열이 있으면 끝난다.
2. 로그에 없으면 **임시 진단 패치**를 만든다. 오류 사유(예외 메시지·오류 코드·타임스탬프)를 화면이나 로그에 찍는 몇 줄이다. 측정 빌드와 별개로 빌드해 기기에 올린다(빌드 수십 초).
3. 진단이 끝나면 패치를 버리고 측정 빌드로 되돌린다. 진단 빌드로 판정을 남기지 않는다.
4. 진단 빌드는 측정이 끝난 뒤(기기가 비었을 때)에만 올린다. 측정 중인 레인의 앱을 바꾸면 그 레인의 판정이 오염된다.

## 5. 셸 함정

- Windows Git Bash 는 `/` 로 시작하는 인자(기기 경로·API 경로)를 `C:/Program Files/Git/…` 로 바꾼다. adb·api 인자에는 `MSYS_NO_PATHCONV=1` 을 붙이거나 PowerShell 에서 부른다.
- PowerShell 파이프로 node/python 에 JSON 을 넘기면 BOM 이 붙어 파싱이 깨질 수 있다. 파일로 쓰고 경로를 넘긴다.
- 따옴표·heredoc·환경변수 export 가 섞인 긴 한 줄 명령은 도구가 실행조차 하지 않고 거부하는 경우가 있다. 스크립트 파일로 감싸 실행한다.
- 콘솔 코드페이지가 UTF-8 이 아니면 한글 출력이 깨져 보인다. 파일은 정상이다. 출력이 깨졌다고 파일을 고치지 않는다.
