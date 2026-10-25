export const meta = {
  name: 'uat-measure',
  description: 'UAT 측정 — API 레인(UI 와 병렬, 서로는 직렬) + UI 레인(기기당 직렬 · after_api 레인은 API 종료 뒤)으로 TC 를 실제로 밟아 판정을 기록한다',
  phases: [
    { title: 'API', detail: 'method=api TC — 전용 계정·전용 클라이언트 IP' },
    { title: 'UI', detail: 'ui_groups 순서대로 · ui_parallel 개씩 · after_api 레인은 마지막' },
  ],
}

// args = plan_lanes.py args 출력(workflow-args.json)
//   { project, run, tools, guide, build, round, prev_rounds:[…], driver, ui_parallel, repo, api:[entry], ui:[entry] }
//   entry = { name, lane, file, n, ids:[…], after_api, model, effort }
// 이 스크립트는 파일을 읽지 못한다 — 레인 에이전트가 프롬프트의 경로를 직접 읽는다.

const A = args
const RUN = A.run
const T = A.tools
const ROUND = A.round || '?'
const PREV = (A.prev_rounds || []).slice().sort((a, b) => b - a)

const RESULT = {
  type: 'object',
  properties: {
    lane: { type: 'string' },
    chunk: { type: 'string' },
    counts: { type: 'object', properties: { P: { type: 'number' }, F: { type: 'number' }, NA: { type: 'number' }, BLOCKED: { type: 'number' } } },
    f_list: { type: 'array', items: { type: 'object', properties: { tc: { type: 'string' }, sev: { type: 'string' }, one_line: { type: 'string' } }, required: ['tc', 'sev', 'one_line'] } },
    blocked: { type: 'array', items: { type: 'object', properties: { tc: { type: 'string' }, why: { type: 'string' } }, required: ['tc', 'why'] } },
    side: { type: 'array', items: { type: 'object', properties: { title: { type: 'string' }, sev: { type: 'string' } }, required: ['title', 'sev'] } },
    fixed_confirmed: { type: 'array', items: { type: 'string' } },
    created_data: { type: 'array', items: { type: 'string' } },
    unjudged: { type: 'array', items: { type: 'string' } },
    end_state: { type: 'string' },
    notes: { type: 'string' },
  },
  required: ['lane', 'chunk', 'counts', 'f_list', 'blocked', 'side', 'fixed_confirmed', 'created_data', 'unjudged', 'end_state', 'notes'],
}

const DRIVER = {
  android: `UI 드라이버 = Android(adb). 도구는 \`python ${T}/android/ui.py\`(dump·tap·type·shot·wait·app·net·log) · 비밀 입력은 \`python ${T}/android/secret_type.py <별칭> <KEY>\`.
- 시작하면 먼저 \`ui.py dump\` 로 지금 화면을 본다. 앞 레인이 가이드의 「레인 시작 상태」로 넘겨줬다.
- 요소는 dump 로 찾고, 판정이 시각(색·대비·잘림·겹침·배치·로딩 종료)에 걸리면 \`ui.py shot <TC-설명>\` 후 .s.png 를 Read 로 열어 눈으로 본다. dump 에 있다고 보이는 것은 아니다.`,
  web: `UI 드라이버 = 웹 브라우저(세션에 연결된 브라우저 자동화 MCP — 가이드 §1 에 적힌 것). 이 레인 전용 탭/컨텍스트만 열고 끝나면 닫는다. 사람이 쓰는 탭은 건드리지 않는다.
- 요소는 접근성 스냅샷으로 찾고, 시각 판정은 스크린샷을 저장해 Read 로 연다(경로는 RUN/shots/<TC-설명>.png).
- 콘솔 오류·실패한 네트워크 요청도 증거다 — 화면이 멀쩡해 보여도 확인한다.`,
}

const COMMON_UI = `UI 레인 공통
- 기기/브라우저 세션은 이 레인 것이다(동시에 도는 UI 레인과 계정·탭을 나눠 쓴다 — 가이드 §0).
- 한 TC 에 같은 조작을 3번 해도 필요한 상태를 못 만들면 BLOCKED(사유·시도한 것)로 적고 다음 TC 로 간다.
- 다른 레인 뒤에 해야 하는 TC(예: 빈 계정·탈퇴 뒤)는 BLOCKED + actual 맨 앞에 [순서 필요: <무엇 뒤>] 를 적는다 — 메인이 모아서 따로 돌린다.
- 레인 끝: 가이드의 「레인 끝 상태」(로그인 계정·첫 화면·네트워크 on·서버 상태)로 돌려놓고 end_state 에 적는다.`

const COMMON_API = `API 레인 공통
- \`python ${T}/api.py [--as <별칭>] METHOD PATH [JSON]\` 만 쓴다. 비밀 값은 {{별칭.KEY}} 자리표시자로 쓴다(값이 출력되지 않는다).
- 🔴 UI 레인이 쓰는 계정의 세션을 끊는 동작(토큰 재사용 폐기·탈퇴·반복 인증 실패)은 금지 — 가이드 §0 의 API 전용 계정으로 한다.
- 클라이언트 IP 축 한도를 재는 TC 는 -H 'X-Forwarded-For: <TC 전용 문서용 IP>' 처럼 전용 값을 써서 다른 레인과 한도를 나누지 않는다(서버가 그 헤더를 믿는 경우).
- 응답의 요지(상태코드·오류 code·핵심 필드)를 evidence 에 적는다.`

function prompt(e, kind) {
  const lane = e.lane || 'api'
  const prevFiles = PREV.map(r => `${RUN}/out/r${r}-${lane}.jsonl`).join(' · ')
  return [
    `너는 ${A.project || ''} UAT **${ROUND}차** 측정 레인 \`${lane}\`(묶음 ${e.name}) 이다. 배정 TC ${e.n}건: ${e.ids.join(', ')}.`,
    `측정만 한다 — 코드·설정·서버를 고치지 않는다. 빌드: ${A.build}. 저장소: ${A.repo || '(가이드 참고)'}.`,
    PREV.length
      ? `배정 TC 는 지난 회차까지 F·BLOCKED 였거나, 등급1 이거나, 수정이 닿은 TC 다 — 처음부터 다시 재서 지금 빌드의 판정을 남긴다.`
      : `1차 전수 측정이다 — 배정 TC 를 원문 절차대로 처음부터 밟는다.`,
    ``,
    `먼저 끝까지 읽을 것(순서대로):`,
    `1) ${A.guide} — 절대 규칙·도구·판정·심각도. 전부 지킨다.`,
    PREV.length ? `2) ${RUN}/lanes/changes.md — 지난 회차 이후 **의도해서 바뀐 동작** · 사람 승인 대기 · 수용된 보류. 여기 적힌 것은 결함으로 판정하지 않는다(승인 대기는 P + note 「승인 대기 …」). 가이드와 다르면 이 파일이 이긴다.` : `2) (1차라 changes.md 없음)`,
    `3) ${RUN}/lanes/notes-${lane}.md — 있으면 이 레인 전용 메모(지난 회차에 쌓인 절차·우회).`,
    `4) ${e.file} — 배정 TC 원문(JSONL, 한 줄 = TC). source 는 기대 결과의 근거 문서다 — 기대문이 모호하거나 화면과 다르면 열어서 확인한다.`,
    PREV.length ? `5) 지난 판정: ${prevFiles} — 지난 F 의 actual·repro 를 보고 **같은 재현 절차로** 다시 밟는다(고쳐졌으면 P + --fix 해소, 아니면 F + 같은 결함임을 note 에).` : ``,
    `판정 기록은 \`python ${T}/verdict.py --lane ${lane} --tc <ID> --v P|F|NA|BLOCKED …\` 로만(P 도 --evidence 필수). TC 밖에서 본 결함은 \`--side\`.`,
    `경로: RUN=${RUN} · T=${T}. 스크립트를 부를 때마다 환경변수 UAT_RUN=${RUN}${A.config ? ` · UAT_CONFIG=${A.config}` : ''} 를 준다(PowerShell: $env:UAT_RUN='…'). 셸 상태는 명령 사이에 남지 않을 수 있다.`,
    ``,
    kind === 'ui' ? (DRIVER[A.driver] || DRIVER.android) + '\n' + COMMON_UI : COMMON_API,
    ``,
    `끝낼 때: \`python ${T}/verdict.py --summary --lane ${lane}\` 로 배정 ID 전부에 판정이 있는지 확인한다(같은 레인 다른 묶음 것도 함께 나온다 — 네 배정 ID 만 본다).`,
    `판정 못 한 TC 는 unjudged 에 넣고 이유를 notes 에. 지난 회차 F 였는데 이번에 P 인 TC 는 fixed_confirmed 에. 만든 데이터(접수번호·계정 별칭)는 created_data 에.`,
    `반환은 구조화 출력 — f_list.one_line 은 「무엇이 어떻게 틀렸나」 한 줄, chunk 는 "${e.name}".`,
  ].filter(Boolean).join('\n')
}

const fail = (e, why) => ({ lane: e.lane || 'api', chunk: e.name, counts: {}, f_list: [], blocked: [], side: [], fixed_confirmed: [], created_data: [], unjudged: e.ids, end_state: why, notes: why })
const opts = (e, label, phase) => {
  const o = { label, phase, schema: RESULT }
  if (e.model) o.model = e.model
  if (e.effort) o.effort = e.effort
  return o
}
const brief = r => `F ${(r.f_list || []).length} · BLOCKED ${(r.blocked || []).length} · 부수 ${(r.side || []).length} · 고쳐짐 ${(r.fixed_confirmed || []).length} · 미판정 ${(r.unjudged || []).length}`

// API 묶음끼리는 직렬 — 같은 전용 계정의 토큰을 둘이 동시에 돌리면 서로의 세션을 끊는다
const apiDone = (async () => {
  const out = []
  for (const e of A.api || []) {
    const r = await agent(prompt(e, 'api'), opts(e, `api:${e.name}`, 'API'))
    out.push(r || fail(e, 'agent 실패(null)'))
    if (r) log(`API ${e.name} 끝 — ${brief(r)}`)
  }
  return out
})()

// UI — after_api 가 아닌 레인을 ui_parallel 개씩, 그 뒤 API 종료를 기다려 after_api 레인
const P = Math.max(1, A.ui_parallel || 1)
const before = (A.ui || []).filter(e => !e.after_api)
const after = (A.ui || []).filter(e => e.after_api)
const ui = []

async function runUi(list) {
  for (let i = 0; i < list.length; i += P) {
    const batch = list.slice(i, i + P)
    batch.forEach(e => log(`UI ${e.name} 시작 (${e.n} TC)`))
    const rs = await parallel(batch.map(e => () => agent(prompt(e, 'ui'), opts(e, `ui:${e.name}`, 'UI'))))
    rs.forEach((r, k) => {
      const e = batch[k]
      ui.push(r || fail(e, 'agent 실패(null)'))
      if (r) log(`UI ${e.name} 끝 — ${brief(r)} · ${String(r.end_state).slice(0, 80)}`)
    })
  }
}

await runUi(before)
if (after.length) {
  log(`after_api 레인 ${after.map(e => e.name).join(', ')}: API 레인 종료 대기`)
  await apiDone
  await runUi(after)
}
const api = await apiDone
const all = [...api, ...ui]
const failed = all.filter(r => (r.unjudged || []).length && !(r.counts && Object.keys(r.counts).length))
if (failed.length) log(`⚠️ 반환이 비었거나 죽은 레인: ${failed.map(r => r.chunk).join(', ')} — 같은 묶음만 새 run 으로 다시 돌린다`)
return { api, ui }
