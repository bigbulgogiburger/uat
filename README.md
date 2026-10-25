# uat — 실제 빌드를 실제로 조작해서 재는 UAT 회차 루프 (Claude Code 스킬)

출시 전 인수 테스트(UAT)를 **에이전트가 실제 앱 화면과 API 를 직접 밟아서** 재고, 확인된 결함만 고친 뒤 같은 방식으로 다시 재는 루프다. Critical·Major 가 0 이 될 때까지 회차를 반복한다.

단위 테스트가 수천 건 초록이어도 실제로 써 보면 깨지는 것들이 있다. 흰 배경에 흰 글씨, 이어 쓰면 제출이 안 되는 폼, 완료 화면 대신 엉뚱한 화면에 남는 이동이 그런 예다. 이 루프는 그런 결함을 잡도록 설계됐다.

## 무엇이 들어 있나

```
uat/
├── SKILL.md                     루프 전체 · 왜 효과가 있었나(10원칙) · 단계별 절차 · 절대 규칙
├── references/                  필요할 때 읽는 상세
│   ├── checklist.md             TC 작성(명세 근거 · 등급 · 저니 · 디자인 일관성)
│   ├── environment.md           프로필 · 외부 발송 차단 · 계정·비밀 · 데이터 시드 · 메모리
│   ├── lanes.md                 레인 분할 · 프롬프트 · Workflow 운용 · 재개
│   ├── drivers.md               Android(adb) · 웹(브라우저 MCP) · API 러너 · 진단 빌드
│   ├── judgment.md              판정 규율 · 심각도 · 감사 · 재확인 · 병합
│   ├── defects-and-fix-loop.md  원인 판독 · 트래커 등록 · 위반 주입 회귀 테스트
│   ├── rounds.md                2차 이후 · changes.md · 보고 · 종료
│   └── lessons.md               실제 사고에서 나온 규칙 25개
├── scripts/                     표준 라이브러리만 쓰는 Python 3.9+
│   ├── init_run.py · tc_merge.py · render_checklist.py · plan_lanes.py
│   ├── verdict.py · triage.py · defects.py · render_results.py
│   ├── sink.py(외부 발송 흉내 수신기) · api.py(비밀 비출력 API 러너) · db.py(원복 기록 DB 러너)
│   ├── android/ui.py · android/secret_type.py · android/ClipSet.java
│   └── memguard.py
└── assets/
    ├── uat.config.example.json  프로젝트 프로필 예시
    ├── templates/               레인 가이드 · TC 작성 지침 · 체크리스트 머리말 · changes · recheck · 결함 이슈 · 드라이버 메모
    ├── workflows/               author.js(TC 작성) · measure.js(측정) · recheck.js(재확인)
    └── examples/                tc · defects · secrets 모양
```

## 설치

```bash
git clone https://github.com/bigbulgogiburger/uat ~/.claude/skills/uat
```

Claude Code 에서 "UAT 돌려줘", "인수 테스트 체크리스트 만들어줘", "2차 UAT 재측정" 같은 말을 하면 스킬이 잡힌다.

## 필요한 것

- Python 3.9+ (스크립트는 표준 라이브러리만 쓴다. `defusedxml` 이 있으면 쓴다)
- Claude Code 의 Workflow 도구(없으면 Agent 도구로 레인을 순차 실행)
- Android: `adb` · 에뮬레이터 또는 기기 / 웹: 브라우저 자동화 MCP 하나
- 선택: 결함 트래커 MCP(Jira 등) · 터미널 멀티플렉서(오래 사는 서버·수신기용)

## 시작하기

1. `assets/uat.config.example.json` 을 복사해 프로젝트 프로필을 만든다(영역·계정 별칭·API·DB·레인 분할).
2. 비밀 값(테스트 계정 번호·인증번호)은 저장소 밖 `secrets_file` 에 둔다. 에이전트는 그 파일을 열지 않는다.
3. 외부 발송(SMS·메일·알림)을 `scripts/sink.py` 로 돌린다.
4. `SKILL.md` 의 "한 바퀴 지도"를 따라 1차 회차를 시작한다.

## 안전 원칙

- 실제 외부 발송 금지 · 비밀 값 비출력 · 인증 우회 금지 · DB 쓰기는 이유와 원복 SQL 과 함께 · 레인은 측정만 한다.
- `verdict.py` · `defects.py` · `tc_merge.py` 는 번호·토큰처럼 보이는 문자열이 든 기록을 거부한다.
