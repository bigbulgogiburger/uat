---
name: uat
description: 출시 전 인수 테스트(UAT)를 "실제 빌드를 실제로 조작해서" 재는 회차 루프. 명세 근거 체크리스트(TC) 작성 → 측정 환경(외부 발송 차단·비밀 격리·데이터 시드) → 에이전트 레인이 화면·API 를 직접 밟아 P/F/N/A/BLOCKED 를 jsonl 로 기록 → 판정 감사·부수 결함 재확인 → Critical/Major/Minor 분류와 원인 판독 → 결함 트래커 등록 → 수정 루프 → 같은 커밋으로 재빌드·재측정을 Critical·Major 0 이 될 때까지 반복한다. Android 에뮬레이터(adb)·웹 브라우저·API 를 같은 틀로 다룬다. "UAT 해줘", "UAT 돌려", "UAT 체크리스트 만들어줘", "인수 테스트", "출시 전 전수 점검", "QA 실측", "재측정", "2차/3차 UAT", "등급1 회귀", "결함 분류해서 Jira 에", "UAT 결과보고", "Critical·Major 0 까지 돌려", "에뮬레이터로 앱 전체 검증" 같은 말이 나오면 스킬 이름을 부르지 않아도 이 스킬을 쓴다. 단위 테스트는 전부 초록인데 실제로 쓰면 깨지는지 확인하고 싶을 때도 여기에 해당한다. 프로젝트 전용 UAT 스킬이 따로 있으면 그쪽을 우선한다.
compatibility: Python 3.9+ · Node 20(Workflow 스크립트) · Claude Code Workflow/Agent 도구(없는 실행기 — Codex 등 — 는 references/lanes.md §9) · (Android) adb · (웹) 브라우저 자동화 MCP 중 하나 · (선택) 결함 트래커 MCP · (선택) Herdr
---

# UAT 회차 루프

출시 전에 **고객이 실제로 쓰는 경로를 실제 빌드에서 직접 밟아** 명세대로 동작하는지 재고, 확인된 결함만 고친 뒤 **같은 방식으로 다시 잰다.** Critical·Major 가 0 이 될 때까지 회차를 돈다.

단위 테스트는 "위젯이 트리에 있다", "함수가 값을 돌려준다"까지만 증명한다. 이 루프가 잡는 것은 그 바깥이다. 예를 들어 흰 배경에 흰 글씨라 제목이 안 보이는 경우, 화면이 다시 그려지며 다음 화면으로 넘어가지 않는 경우, 이어 쓰기를 하면 앞 단계에서 확정한 값이 사라지는 경우가 그렇다. 이런 결함은 테스트 수천 건이 전부 초록인 채로 살아 있었다.

## 왜 효과가 있었나 — 규칙을 줄이고 싶어지면 여기부터 다시 읽는다

이 스킬의 절차는 실제 회차를 돌면서 **기대보다 결과가 좋았던 이유**를 그대로 옮긴 것이다. 각 항목이 빠지면 무엇이 무너지는지도 같이 적었다.

1. **기대 결과는 명세에서 온다. 코드에서 베끼지 않는다.** TC 마다 `source`(근거 문서 경로)를 단다. 코드를 읽는 이유는 조작 절차(버튼 문구·진입 경로)를 쓰기 위해서다. 코드와 명세가 다르면 그 차이 자체를 `notes` 에 결함 후보로 남긴다. 코드를 베낀 기대문으로 재면 결함이 전부 P 로 통과한다.
2. **사람이 그대로 따라 할 수 있는 TC.** 절차는 화면에 보이는 버튼 문구로 쓰고, 기대는 관찰 가능한 것만 쓴다. "정상 동작"이라고 쓰면 판정이 레인마다 갈린다.
3. **강한 모델이 진짜로 밟는다.** 레인은 최상위 모델·높은 추론 강도로 돌리고, 실제 화면(dump + 스크린샷)과 실제 API 응답을 증거로 남긴다. P 에도 증거가 필수다. 증거 없는 P 는 "안 해 봤다"와 구별되지 않는다.
4. **판정 규율이 오판을 막는다.** "화면에 없다"로 F 를 주기 전에 스크롤·다른 탭·dump·스크린샷을 모두 본다. 기대문이 의심스러우면 F 대신 BLOCKED("기대문 의심")로 둔다. 시각 판정은 스크린샷을 직접 열어서 한다. 1차 판정은 틀리므로 메인이 감사한다.
5. **TC 밖에서 본 것도 버리지 않는다.** 측정 중 눈에 띈 결함은 부수(side) 결함으로 기록한다. 다음 회차에는 전용 재확인 레인이 그 재현 절차를 다시 밟는다. 실제로 Major 의 상당수가 부수 기록에서 나왔다.
6. **결함은 원인까지 읽고 등록한다.** 트래커에 올리기 전에 메인이 코드를 읽어 원인과 수정 방향을 적는다. 증상을 원인으로 단정하기 전에 진짜 오류 문자열(로그·응답 바디)을 먼저 손에 넣는다.
7. **고친 것은 "그 결함이 다시 나면 빨개지는" 회귀 테스트로 증명한다.** 수정을 되돌리는 위반을 주입했을 때 테스트가 단언으로 실패하는지 본다. 판정은 종료 코드가 아니라 출력(실패 블록·태그)으로 한다. 컴파일이 깨져서 빨개진 것은 증명이 아니다.
8. **회차마다 "무엇이 바뀌었나"를 레인에게 준다.** `changes.md` 에는 의도해서 바뀐 동작, 사람 승인 대기, 수용된 보류를 적는다. 이게 있어야 의도한 변경을 결함으로 잡지 않고, 지난 F 를 같은 재현 절차로 다시 밟는다.
9. **한 회차 = 한 빌드 = 한 커밋.** 서버와 클라이언트를 같은 커밋으로 빌드한다. 회차 중간에 빌드를 바꾸면 어떤 판정이 어느 코드에 대한 것인지 알 수 없게 된다.
10. **안전장치가 측정을 가능하게 한다.** 외부 발송은 로컬 수신기로 차단하고, 비밀 값은 출력에 남지 않게 다룬다. 데이터는 접두어를 붙여 만들고 원복 기록을 남긴다. 이게 없으면 "실제로 눌러 보기"를 할 수 없다.

## 용어

| 말 | 뜻 |
|---|---|
| **TC** | 체크리스트 한 줄. `A-01` 처럼 영역 문자 + 순번. 사용자가 하는 일 하나에 TC 하나 |
| **등급** | 1 = 출시 필수(핵심 여정·보안·데이터 정합) · 2 = 주요 기능·주요 예외 · 3 = 보조 상태·디자인 세부 |
| **P / F / NA / BLOCKED** | 기대대로(증거 필수) / 다름(심각도·재현 절차 필수) / 범위 밖으로 확정됨 / 이 환경에서 판정 불가(사유 필수) |
| **Critical · Major · Minor** | F·부수 결함의 심각도. 기준은 [references/judgment.md](references/judgment.md) §3 |
| **레인** | TC 묶음 하나를 맡아 실제로 재는 에이전트 한 명. 자원(기기·계정)을 배타적으로 갖는다 |
| **부수(side) 결함** | TC 밖에서 측정 중에 본 결함 |
| **회차(round)** | 한 빌드로 재는 한 바퀴. 1차는 전수, 2차부터는 재측정(등급1 ∪ 지난 F·BLOCKED ∪ 미해결 결함 TC ∪ 사람 확인 TC) |
| **GO 기준** | 미해결 확정 결함 Critical 0 · Major 0, 그리고 등급1 전부 P · NA · 수용된 보류 |

## 한 바퀴 지도

```
[0 전제] 무엇을 재나(커밋) · 메모리 · 서버/기기 · 외부 발송 차단
   ↓
[1 회차 폴더] init_run.py ─ run.json · (2차부터) 지난 판정을 r<N>- 로 보존
   ↓
[2 체크리스트] (1차) author 워크플로 → tc_merge.py → render_checklist.py      ── 2차부터는 기대문 정정만
   ↓
[3 레인 계획] plan_lanes.py full | remeasure → lanes/*.jsonl · manifest · workflow-args.json
   ↓
[4 측정] Workflow measure.js ─ API 레인(병렬) + UI 레인(기기당 직렬) → out/<lane>.jsonl
   ↓
[5 감사] triage.py · F/BLOCKED 직접 대조 · recheck 워크플로(부수·빈 계정) → defects.json
   ↓
[6 분류·등록] 심각도 재판정 · 코드로 원인 판독 · 트래커 부모 1 + 하위 N
   ↓
[7 수정 루프] 이슈별 브랜치(쌓기) · 위반 주입으로 증명한 회귀 테스트 · 리뷰 · 게이트 · 사람 머지
   ↓
[8 재빌드] 스택 끝 커밋 하나로 서버·앱 → changes.md · recheck.md
   ↓
[9 보고·판정] render_results.py → GO 면 끝, 아니면 [1] 로 (다음 회차)
   ↓
[10 정리] 시드한 상태 원복 · 기기 설정 원복 · 만든 데이터 목록
```

## 경로

```bash
SKILL=~/.claude/skills/uat ; S=$SKILL/scripts
export UAT_CONFIG=<프로젝트 프로필>/uat.config.json        # 프로젝트당 1개 — assets/uat.config.example.json 참고
export UAT_RUN=<runs_dir>/<YYYY-MM-DD>-uat<N>               # 회차마다 새 폴더
# PowerShell: $env:UAT_CONFIG='…' ; $env:UAT_RUN='…'  (출력이 깨지면 $env:PYTHONIOENCODING='utf-8')
```

모든 스크립트는 실행 폴더를 `--run` > `UAT_RUN` > 현재 폴더에서 위로 올라가며 찾은 `run.json` 순서로 정한다. 프로필은 `--config` > `UAT_CONFIG` > `run.json` 의 `config` 순서로 찾는다. 옵션은 각 스크립트의 `--help` 로 본다.

- **판정 원본은 실행 폴더의 jsonl 이다.** 세션 scratchpad 는 세션과 함께 사라지므로 거기 두지 않는다. 문서(md·xlsx)는 jsonl 에서 렌더한 산출물일 뿐이다.
- **비밀 파일**(`secrets_file` — 계정 번호·인증번호·비밀번호·토큰)은 스크립트만 읽는다. 에이전트는 그 파일을 열어 보지 않는다. 화면에 비밀 값을 입력할 때는 `secret_type.py` 를, API 를 부를 때는 `api.py` 의 `{{alias.KEY}}` 자리표시자를 쓴다. 두 도구 모두 값을 출력하지 않는다.

## 처음 쓰는 프로젝트 — 프로필 만들기

`assets/uat.config.example.json` 을 복사해 채운다. 코드와 설정을 읽어서 알 수 있는 값은 사용자에게 묻지 않는다. 사용자에게 물을 것은 다음뿐이다.

- **테스트 계정**과 그 비밀 값을 어디에 둘지(저장소 밖 경로)
- **외부로 나가는 발송 경로**(SMS·알림톡·메일·푸시·결제·세금계산서)가 무엇이고, 어떻게 로컬로 돌릴지
- **측정 대상 환경**(로컬 서버 / 공유 dev / QA 배포)과 거기서 DB 쓰기를 허용할지
- **결함 트래커**(프로젝트 키·부모 이슈·담당자)와 수정 루프 방식
- **되돌릴 수 없는 동작** 목록(탈퇴할 계정, 실결제, 실발행 등) — 레인 가이드의 절대 규칙이 된다

프로필 항목 설명은 [references/environment.md](references/environment.md) §1.

## 단계별

### 0. 전제 — 무엇을 재는지부터 고정한다

재는 빌드가 생각과 다르면 회차 전체가 헛돈다.

- 서버와 클라이언트 빌드가 **같은 커밋**인지 확인한다. 커밋 sha 는 `run.json` 과 보고서에 적는다.
- 공유 DB 스키마가 그 커밋이 기대하는 버전인지 확인한다. 환경 갭(마이그레이션 누락)을 제품 결함으로 적으면 안 된다.
- 외부 발송 차단(`sink.py`)과 서버·에뮬레이터는 **오래 사는 별도 터미널(pane)** 에 띄운다. 에이전트 세션의 백그라운드 셸은 메모리가 모자랄 때 정리돼 측정 도중 서버가 사라진다.
- 여유 메모리를 본다(`memguard.py`). 측정 중에는 전량 빌드·테스트·코드 생성을 돌리지 않는다. 기기·서버·레인이 같이 메모리를 쓴다.

### 1. 회차 폴더

```bash
python $S/init_run.py --round 1 --build <sha> [--date 2026-10-23]                 # 1차
python $S/init_run.py --round 3 --build <sha> --prev <2차 RUN>                     # 2차부터
```

2차부터는 지난 회차의 `tc.jsonl`·`defects.json`·`work/` 상태 파일을 이어받는다. 지난 판정은 `out/r<N>-<lane>.jsonl` 로 보존한다. TC 판정은 **가장 나중 기록이 이기므로** 새 판정이 옛 판정을 덮는다. 직전 폴더에 이어 쓰지 않는다.

### 2. 체크리스트 — 1차에 한 번, 이후에는 정정만

1차는 영역 묶음별 작성 레인이 병렬로 TC 초안을 쓴다. 근거 문서를 읽고, 조작 절차를 쓰기 위해 화면 코드를 읽는다.

```bash
# assets/templates/tc-brief.md 를 RUN/tc-brief.md 로 복사해 프로젝트 사실(환경·계정·미구현 목록)을 채운다
Workflow scriptPath=$SKILL/assets/workflows/author.js args={run, brief, groups:[{name, areas, docs[], code[]}]}
python $S/tc_merge.py                  # tc-draft/*.jsonl → tc.jsonl (필수 필드·중복·영역 검사)
python $S/render_checklist.py --head RUN/checklist-head.md --out <repo>/docs/UAT_체크리스트.md
```

- 작성 규칙(스키마·등급·feasibility·데이터 준비·디자인 일관성 TC·종단 저니)은 [references/checklist.md](references/checklist.md).
- 2차부터 기대문이 틀렸다고 확인되면(사람 결정·명세 갱신) `tc.jsonl` 의 그 줄을 고치고 `notes` 에 바꾼 이유를 남긴다. 틀린 기대문으로 재면 틀린 F 가 나온다.
- Figma 같은 시안은 계속 바뀐다. 화면 착수 직전과 재측정 직전에 다시 읽는다.

### 3. 측정 환경

[references/environment.md](references/environment.md) 를 따른다. 요지는 다음과 같다.

- **외부 발송 차단**: SMS·알림톡·메일 HTTP/SMTP 를 `sink.py` 로 돌린다. 수신기 로그(경로·크기·시각만 남는다)로 "보냈는가"를 판정할 수 있다. 수신기를 거치지 않은 실제 발송 흔적이 보이면 즉시 멈춘다.
- **계정 분할**: UI 레인과 API 레인이 같은 계정의 세션을 동시에 쓰지 않게 나눈다. 세션 파괴(탈퇴·토큰 재사용 폐기)는 전용 계정으로, 다른 레인이 끝난 뒤에 한다.
- **데이터**: 만드는 데이터에는 `data_prefix`(예: `UAT`)를 붙인다. 앱이 만들 수 없는 상태(배정·완료 등)는 **프로젝트 상태 시드 도구 하나로만** 만든다. 그 도구는 처음 값을 스냅샷하고 원복할 수 있어야 한다. 직접 UPDATE 를 흩뿌리지 않는다.
- **비밀**: `secret_type.py`(화면 입력), `api.py`(자리표시자), `verdict.py`(번호·토큰 꼴 문자열이 있으면 기록을 거부)가 3중으로 막는다.

### 4. 레인 계획

```bash
python $S/plan_lanes.py full                                   # 1차: 전 TC
python $S/plan_lanes.py remeasure [--extra D-12,M-04]          # 2차~: 등급1 ∪ 지난 F·BLOCKED ∪ 미해결 결함 TC ∪ extra
python $S/plan_lanes.py args --model opus --effort xhigh --out RUN/lanes/workflow-args.json
```

- `method=api` TC 는 API 레인으로 간다. API 레인은 UI 와 병렬로 돌고, 같은 계정 토큰을 돌리는 것끼리는 직렬이다.
- UI 레인은 프로필의 `ui_groups` 순서대로, **기기 하나당 동시에 하나만** 돈다. 웹이라 브라우저 컨텍스트를 나눌 수 있으면 `ui_parallel` 을 올린다.
- 세션·상태를 파괴하는 레인(`after_api`)과 서버 재기동이 필요한 TC(`isolated`)는 다른 레인이 끝난 뒤에 돈다.
- 한 레인은 `chunk`(기본 16) TC 를 넘지 않게 자른다. 길어지면 에이전트가 앞 규칙을 잊는다.

설계 근거와 레인 프롬프트 구성은 [references/lanes.md](references/lanes.md).

### 5. 측정

```bash
cp $SKILL/assets/templates/lane-guide.md RUN/lane-guide.md      # 1차: 절대 규칙·도구·판정을 프로젝트에 맞게 채운다
Workflow scriptPath=$SKILL/assets/workflows/measure.js args=@RUN/lanes/workflow-args.json
```

- 레인은 순서대로 읽는다: ① 레인 가이드 ② `lanes/changes.md`(2차부터, 이게 기준) ③ `lanes/notes-<lane>.md`(지난 회차에 쌓인 레인 전용 절차·우회) ④ 배정 TC ⑤ 지난 판정(`out/r<N>-<lane>.jsonl`). 지난 F 는 **같은 재현 절차로** 다시 밟는다.
- 판정은 `verdict.py` 로만 기록한다. 레인은 코드·설정을 고치지 않는다.
- 레인 반환은 구조화 출력이다: counts · f_list · blocked · side · fixed_confirmed · created_data · unjudged · end_state. **완주 여부는 반환값으로 판정한다.** 파일이 있다는 것만으로 끝났다고 보지 않는다.
- 측정이 도는 동안 메인은 다른 일을 해도 된다(이전 회차 결함의 원인 판독, 수정 계획 등). 단, 빌드·테스트·게이트는 측정이 끝난 뒤에 돌린다.

### 6. 감사 — 1차 판정을 그대로 내지 않는다

```bash
python $S/triage.py [--json RUN/triage.json]    # 결함별 재발/고쳐짐 후보/미확인 · 새 F · 부수 · BLOCKED · 등급1 잔여
```

메인이 직접 한다. 순서와 함정은 [references/judgment.md](references/judgment.md) §4~§6.

- **F 마다** actual·evidence·repro 를 읽는다. 스크린샷 증거는 직접 연다. "없다"류 F, 문구 차이 F, 기대문이 의심스러운 F 는 근거 문서를 다시 연다.
- **BLOCKED 마다** 사유가 환경 한계(실기기·외부 계정·푸시)인지, 레인이 길을 못 찾은 것인지 가른다. 후자는 재도전 레인으로 보낸다. "빈 계정 필요"처럼 다른 레인 뒤에 해야 하는 것은 묶어서 따로 돌린다.
- **부수 결함**은 `lanes/recheck.md` 에 재현 절차와 고쳐진 동작을 적고 `recheck.js` 로 다시 밟는다. 재현된 것만 확정한다.
- 확정한 결함을 `defects.py add` 로 `defects.json` 에 올린다. 확정 기준: 재확인 재현 · 두 레인 이상의 독립 관측 · 두 회차 연속 같은 F · 코드로 원인 확인.

### 7. 분류·등록

- 심각도는 레인이 붙인 값을 그대로 쓰지 않는다. 기준표([references/judgment.md](references/judgment.md) §3)로 다시 매긴다. 레인은 Major/Minor 로 낮게 적는 경향이 있다. "핵심 여정을 끝까지 못 감"이면 Critical 이다.
- **등록 전에 원인을 읽는다**: 증상 → 관련 코드 경로 → 원인 가설 → 확인. 원인을 못 찾았으면 "추정"이라고 쓰고 진단 절차(실기 로그 확보 등)를 수정 방향의 첫 줄에 둔다.
- 트래커 구조: 회차별 부모 1개("[UAT N차] 결함 수정 — Critical·Major 0 까지") + 같은 원인끼리 묶은 하위 이슈. 본문 템플릿은 `assets/templates/defect-issue.md`(현상 · 원인 · 수정 방향 · 영향 TC · 범위 밖). 재현에 쓴 데이터는 별칭(계정#1)으로만 쓴다.
- 등록 절차와 중복 방지는 [references/defects-and-fix-loop.md](references/defects-and-fix-loop.md) §1~§3.

### 8. 수정 루프

- 하위 이슈 묶음마다 브랜치 하나를 쓰고, 직전 묶음 위에 쌓는다. 머지는 사람이 한다. 프로젝트에 이슈 하네스(게이트·리뷰·커밋 훅)가 있으면 그것을 쓴다.
- 각 수정에는 **결함이 다시 나면 단언으로 빨개지는** 회귀 테스트를 붙인다. 실물 흐름(실제 화면·실제 라우터)으로 세우고, 수정을 되돌리는 위반 주입으로 빨개지는지 확인한다. 판정은 출력의 실패 블록으로 한다. 상세는 [references/defects-and-fix-loop.md](references/defects-and-fix-loop.md) §4.
- 서버를 고쳐야 하는 결함이면 그 서버 저장소에 따로 브랜치를 판다. 필요 없으면 손대지 않는다.
- 측정 기기가 도는 동안에는 테스트·게이트를 돌리지 않는다. 측정이 끝난 뒤 한 번에 돌린다.

### 9. 재빌드·재측정·보고

```bash
python $S/init_run.py --round <N+1> --build <스택 끝 sha> --prev <N차 RUN>
# RUN/lanes/changes.md  ← assets/templates/changes.md : 이번에 의도해서 바뀐 동작(이슈별) · 승인 대기 · 수용된 보류 · 지난 회차 내용 누적
# RUN/lanes/recheck.md  ← assets/templates/recheck.md : TC 밖 부수 결함의 재현 절차와 고쳐진 동작
python $S/plan_lanes.py remeasure && python $S/plan_lanes.py args --out RUN/lanes/workflow-args.json
python $S/render_results.py --round <N> --date <YYYY-MM-DD> --build <sha> --out <repo>/docs/UAT_결과보고.md [--note "실측 117 TC …"]
```

- 결과보고에는 회차마다 절을 하나씩 둔다. 같은 회차 절은 덮어쓰고 다른 회차 절은 보존한다.
- 판정은 GO/NO-GO 하나로 낸다. 숫자는 손으로 옮기지 않고 스크립트 출력에서 가져온다.
- 사용자에게 보고할 때는 결함 ID 가 아니라 **"화면에서 무엇이 잘못 보이나"부터 쉬운 말로** 쓴다.

### 10. 정리 — 루프가 끝나거나 멈출 때

- 상태 시드 도구로 손댄 행을 원복한다(`revert`). 직접 쓴 DB 행은 `work/db-writes.log` 의 원복 SQL 로 되돌린다.
- 기기 설정(키보드·글자 크기·회전·네트워크)을 되돌린다. 만든 데이터 목록(`work/requests.jsonl`)을 보고서에 남긴다.
- 띄운 수신기·서버·에뮬레이터 pane 중 더 쓰지 않을 것은 닫는다.

## 절대 규칙 — 메인과 모든 레인 공통

레인 가이드 템플릿 §0 에 같은 내용이 들어 있다. 프로젝트별 금지 동작을 더해서 쓴다.

1. **외부로 실제 발송하지 않는다**(SMS·알림·메일·푸시·결제·세금계산서·외부 웹훅). 차단할 수 없는 발송 버튼은 누르지 않고, 그 뒤 단계는 NA 나 수용된 보류로 둔다.
2. **비밀 값을 읽어서 출력하거나 기록하지 않는다.** 파일·로그·보고서·트래커·최종 답 어디에도 쓰지 않는다. 계정은 별칭(`계정#1`)으로만 부른다.
3. **인증을 우회하지 않는다.** DB 에서 토큰·OTP 를 꺼내거나 만드는 것은 측정이 아니라 침입이다.
4. **DB 쓰기는 최후 수단이다.** UAT 가 만든 행에만, 이유와 원복 SQL 과 함께 쓴다. 읽기는 자유다.
5. **레인은 측정만 한다.** 코드·설정·서버를 고치지 않고, 서버를 임의로 재시작하지 않는다(TC 가 장애를 요구할 때만 내렸다 올린다).
6. **되돌릴 수 없는 전이**(완료·취소·탈퇴)는 이번 회차에 레인이 새로 만든 데이터·전용 계정으로만 한다.
7. **측정 중에는 무거운 빌드·테스트를 돌리지 않는다.** 메모리가 레인 수를 정한다.
8. **루트부터 파일을 찾는 명령(`find /` 류)을 쓰지 않는다.** 저장소 안에서 Grep/Glob 으로 찾는다.

## 멈출 때와 끝날 때

- **끝**: 미해결 확정 결함 Critical 0 · Major 0, 그리고 등급1 전부 P · NA · 수용된 보류. Minor 는 목록으로 남기고 가능한 것은 함께 고친다.
- **멈추고 보고**: ① 같은 결함이 2회차 연속 해소되지 않음 ② 여유 메모리 < 1.5GB(새 레인 금지) ③ 같은 게이트가 2회 연속 실패 ④ 실제 외부 발송 흔적 ⑤ 사람만 정할 수 있는 결정(기대문 충돌·범위·디자인 판단)이 결함 판정을 막음.
- 사람 결정이 필요한 항목은 회차 중에 하나씩 묻지 않는다. "승인 대기"로 `changes.md` 에 적고 계속 잰다. 사용자에게는 회차가 끝날 때 한 번에 묻는다.
- 결정 대기로 넘긴 것(수용된 보류·승인 대기)은 GO 판정에서 어떻게 셌는지 보고서에 그대로 적는다.

## 실행 폴더 구조

```
<runs_dir>/
  uat.config.json? (또는 프로젝트 저장소에)        lane-guide.md (프로젝트용으로 채운 가이드 — 회차 간 공유)
  <YYYY-MM-DD>-uat<N>/
    run.json · tc.jsonl · tc-brief.md · checklist-head.md
    tc-draft/<group>.jsonl                                       (1차 작성 레인 산출)
    lanes/<lane>-<k>.jsonl · manifest.json · workflow-args.json · changes.md · recheck.md · notes-<lane>.md · why.json
    out/<lane>.jsonl · out/r<N>-<lane>.jsonl(지난 회차)
    shots/<tc>-<설명>.png(.s.png 축소본)
    work/ requests.jsonl · db-writes.log · state-snapshots.json · sink.log · driver-notes.md · 빌드 산출물
    defects.json · triage.json
```

## 참조

| 파일 | 언제 읽나 |
|---|---|
| [references/checklist.md](references/checklist.md) | 1차 TC 작성 · 기대문 정정 · 저니 설계 |
| [references/environment.md](references/environment.md) | 프로필 작성 · 외부 발송 차단 · 계정·비밀 · 데이터 시드 · pane 운용 |
| [references/lanes.md](references/lanes.md) | 레인 분할 · 프롬프트 구성 · Workflow 운용 · 감시 · 재개 |
| [references/drivers.md](references/drivers.md) | Android(adb) · 웹(브라우저 MCP) · API 러너의 쓰는 법과 함정 |
| [references/judgment.md](references/judgment.md) | 판정 규율 · 심각도 · 감사 · 재확인 · 병합 |
| [references/defects-and-fix-loop.md](references/defects-and-fix-loop.md) | 결함 확정 · 원인 판독 · 트래커 등록 · 수정 루프 · 위반 주입 회귀 테스트 |
| [references/rounds.md](references/rounds.md) | 2차 이후: 재빌드 · changes.md · 재측정 범위 · triage · 보고 · 종료 |
| [references/lessons.md](references/lessons.md) | 실제 사고에서 나온 규칙 목록 — 규칙이 왜 있는지 궁금할 때 |

| 스크립트 | 하는 일 |
|---|---|
| `init_run.py` | 회차 폴더 · run.json · 지난 회차 이어받기 |
| `tc_merge.py` · `render_checklist.py` | TC 초안 병합·검증 · 체크리스트 문서 렌더 |
| `plan_lanes.py` | `full` / `remeasure` 레인 분할 · `args` Workflow 인자 |
| `verdict.py` | 판정·부수 결함 1건 기록(필수 필드·비밀 패턴 검사) · `--summary` |
| `triage.py` · `defects.py` | 회차 판정 분류 · 결함 목록 관리(add·set·list) |
| `render_results.py` | 결과보고 회차 절 렌더 · `--stats` |
| `sink.py` | 외부 발송 흉내 수신기(HTTP·SMTP) |
| `api.py` · `db.py` | API 러너(자리표시자·마스킹·로그인 시퀀스) · DB 러너(쓰기 = 이유+원복 필수) |
| `android/ui.py` · `android/secret_type.py` | adb 화면 조작(dump·tap·type·shot·net) · 비밀 값 입력 |
| `memguard.py` | 여유 메모리 확인 · 측정 전 점검 |
| `selftest.py` | 설치 확인 — 가상 프로젝트로 1차→2차 파이프라인을 기기 없이 돌린다 |

| 자산 | 용도 |
|---|---|
| `assets/uat.config.example.json` | 프로젝트 프로필 예시 |
| `assets/templates/*.md` | 레인 가이드 · TC 작성 지침 · 체크리스트 머리말 · changes · recheck · 결함 이슈 본문 · 드라이버 메모 |
| `assets/workflows/*.js` | author(TC 작성) · measure(측정) · recheck(재확인·빈 계정) |
| `assets/examples/*` | tc · defects · secrets 모양 예시 |
