export const meta = {
  name: 'uat-recheck',
  description: 'UAT 보충 — TC 밖 부수 결함을 재현 절차로 다시 밟고(fixed/still/blocked), 순서가 필요한 TC(빈 계정·탈퇴 뒤 등)를 따로 잰다',
  phases: [
    { title: 'Recheck', detail: 'lanes/recheck.md 의 항목마다 재현 절차 → 고쳐진 동작 확인' },
    { title: 'Ordered', detail: '다른 레인 뒤에 해야 하는 TC 묶음' },
  ],
}

// args = { project, run, tools, guide, build, driver, recheck:[결함 ID…], ordered:[TC…], ordered_how:"빈 계정을 만드는 절차", model?, effort? }

const A = args
const RUN = A.run
const T = A.tools

const RECHECK = {
  type: 'object',
  properties: {
    items: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          result: { type: 'string', enum: ['fixed', 'still', 'blocked'] },
          sev: { type: 'string' },
          evidence: { type: 'string' },
          note: { type: 'string' },
        },
        required: ['id', 'result', 'evidence', 'note'],
      },
    },
    side: { type: 'array', items: { type: 'object', properties: { title: { type: 'string' }, sev: { type: 'string' } }, required: ['title', 'sev'] } },
    created_data: { type: 'array', items: { type: 'string' } },
    end_state: { type: 'string' },
    notes: { type: 'string' },
  },
  required: ['items', 'side', 'created_data', 'end_state', 'notes'],
}

const LANE = {
  type: 'object',
  properties: {
    counts: { type: 'object', properties: { P: { type: 'number' }, F: { type: 'number' }, NA: { type: 'number' }, BLOCKED: { type: 'number' } } },
    f_list: { type: 'array', items: { type: 'object', properties: { tc: { type: 'string' }, sev: { type: 'string' }, one_line: { type: 'string' } }, required: ['tc', 'sev', 'one_line'] } },
    blocked: { type: 'array', items: { type: 'object', properties: { tc: { type: 'string' }, why: { type: 'string' } }, required: ['tc', 'why'] } },
    side: { type: 'array', items: { type: 'object', properties: { title: { type: 'string' }, sev: { type: 'string' } }, required: ['title', 'sev'] } },
    end_state: { type: 'string' },
    notes: { type: 'string' },
  },
  required: ['counts', 'f_list', 'blocked', 'side', 'end_state', 'notes'],
}

const common = [
  `먼저 끝까지 읽을 것: 1) ${A.guide}(절대 규칙·도구·판정) 2) ${RUN}/lanes/changes.md(지난 회차 이후 의도해서 바뀐 동작 — 이것이 기준)`,
  `경로: RUN=${RUN} · T=${T}. 측정만 한다 — 코드·설정·서버를 고치지 않는다. 빌드: ${A.build}.`,
  A.driver === 'web'
    ? `UI 는 이 레인 전용 브라우저 탭/컨텍스트로만. 시각 판정은 스크린샷을 저장해 Read 로 연다.`
    : `기기는 이 레인만 쓴다. 시작하면 \`python ${T}/android/ui.py dump\` 로 지금 화면부터 본다. 시각 판정은 \`ui.py shot recheck-<id>-<설명>\` 후 .s.png 를 Read 로 연다.`,
]

const opt = (label, phase, schema) => {
  const o = { label, phase, schema }
  if (A.model) o.model = A.model
  if (A.effort) o.effort = A.effort
  return o
}

const out = {}
if ((A.recheck || []).length) {
  phase('Recheck')
  out.recheck = await agent([
    `너는 ${A.project || ''} UAT **부수 결함 재확인** 레인이다. 대상: ${A.recheck.join(', ')}.`,
    `항목마다 ${RUN}/lanes/recheck.md 의 재현 절차를 **그대로** 밟는다. 「고쳐진 동작」이 보이면 fixed, 예전 현상이 다시 보이면 still,`,
    `이 환경에서 재현 조건을 못 만들면 blocked(사유 · 시도한 것). 갈래가 여럿인 항목은 갈래마다 보고, 하나라도 예전 현상이면 still 이고 그 갈래를 note 에 적는다.`,
    ...common,
    `결과는 구조화 출력으로만 돌려준다(verdict.py 로 쓰지 않는다). 재확인 목록 밖에서 새로 본 결함은 side 에(심각도는 가이드 기준).`,
    `손댄 데이터는 가이드대로 원복하고, 원복하지 못한 것은 created_data 와 notes 에 남긴다.`,
  ].join('\n'), opt('recheck', 'Recheck', RECHECK))
}
if ((A.ordered || []).length) {
  phase('Ordered')
  out.ordered = await agent([
    `너는 ${A.project || ''} UAT **순서 필요 TC 재측정** 레인이다. 대상 TC: ${A.ordered.join(', ')} — 이번 회차 레인이 「[순서 필요 …]」로 BLOCKED 한 것들이다.`,
    `TC 원문은 ${RUN}/tc.jsonl 에서 id 로 찾고, 이번 회차 BLOCKED 기록은 ${RUN}/out/*.jsonl(r<N>- 접두가 아닌 파일)에 있다.`,
    `필요한 상태를 만드는 절차: ${A.ordered_how || '(가이드 참고)'}`,
    ...common,
    `판정은 \`python ${T}/verdict.py --lane ordered --tc <ID> --v P|F|NA|BLOCKED …\` 로 기록한다(가장 나중 기록이 이긴다). 끝나면 가이드의 「레인 끝 상태」로 돌려놓는다.`,
  ].join('\n'), opt('ordered', 'Ordered', LANE))
}
return out
