export const meta = {
  name: 'uat-author',
  description: 'UAT 1차 체크리스트 작성 — 영역 묶음별 레인이 명세 근거 문서와 화면 코드를 읽고 TC 초안(tc-draft/<묶음>.jsonl)을 쓴 뒤, 비평 레인이 빠진 사용자 행동·근거 없는 기대문을 찾아 보강한다',
  phases: [
    { title: 'Draft', detail: '묶음별 TC 초안 — 근거 문서에서 기대 결과, 화면 코드에서 조작 절차' },
    { title: 'Critique', detail: '빠진 사용자 행동·예외·디자인 일관성 TC · 근거 없는 기대문 · 비밀 값' },
  ],
}

// args = { project, run, repo, brief: "RUN/tc-brief.md", groups: [{ name, areas: ["D","E"], docs: [경로…], code: [경로…], hint?: "…" }], model?, effort?, critique?: true }

const A = args
const RUN = A.run

const DRAFT = {
  type: 'object',
  properties: {
    group: { type: 'string' },
    file: { type: 'string' },
    count: { type: 'number' },
    by_grade: { type: 'object', properties: { g1: { type: 'number' }, g2: { type: 'number' }, g3: { type: 'number' } } },
    defect_candidates: { type: 'array', items: { type: 'string' } },
    no_source: { type: 'array', items: { type: 'string' } },
    unknowns: { type: 'array', items: { type: 'string' } },
  },
  required: ['group', 'file', 'count', 'by_grade', 'defect_candidates', 'no_source', 'unknowns'],
}

const CRIT = {
  type: 'object',
  properties: {
    added: { type: 'number' },
    fixed: { type: 'number' },
    gaps_left: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
  required: ['added', 'fixed', 'gaps_left', 'notes'],
}

const opt = (label, phase, schema) => {
  const o = { label, phase, schema }
  if (A.model) o.model = A.model
  if (A.effort) o.effort = A.effort
  return o
}

const draftPrompt = g => [
  `너는 ${A.project || ''} UAT 1차 체크리스트의 **${g.name}** 묶음(영역 ${g.areas.join('·')}) TC 초안을 쓴다.`,
  `먼저 ${A.brief} 를 끝까지 읽는다 — 측정 환경·TC 스키마·등급·feasibility·하지 말 것이 전부 거기 있다.`,
  `저장소: ${A.repo}. 기대 결과의 근거 문서(이것만 기대문의 출처다):`,
  ...(g.docs || []).map(d => `- ${d}`),
  `조작 절차를 쓰기 위해 읽을 화면·라우트 코드(기대문을 여기서 베끼지 않는다 — 명세와 다르면 notes 에 결함 후보로):`,
  ...(g.code || []).map(d => `- ${d}`),
  g.hint ? `묶음 메모: ${g.hint}` : '',
  ``,
  `산출: ${RUN}/tc-draft/${g.name}.jsonl — JSON 한 줄 = TC. id 는 영역 문자 + 두 자리 순번. 이 파일만 쓴다(다른 파일·코드 수정 금지, 앱·서버 실행 금지).`,
  `사용자가 하는 일 하나에 TC 하나 — 정상 경로 + 중요한 예외(필수값·길이·중복·권한·네트워크 실패·뒤로가기) + 이 영역 화면끼리 같아야 할 디자인 일관성.`,
  `근거를 못 찾은 기대문은 지어내지 말고 notes 에 「근거 미확인」. 비밀 값(번호·인증번호·토큰)은 쓰지 않고 별칭(계정#1)으로.`,
  `반환: group · file · count · by_grade · defect_candidates(코드와 명세가 다른 것 — 「TC id: 무엇이」) · no_source(근거 미확인 TC id) · unknowns.`,
].filter(Boolean).join('\n')

const critPrompt = (g, d) => [
  `너는 ${A.project || ''} UAT 체크리스트 **비평 레인**이다. 대상: ${RUN}/tc-draft/${g.name}.jsonl (${d ? d.count : '?'} TC, 영역 ${g.areas.join('·')}).`,
  `${A.brief} 의 규칙을 기준으로, 근거 문서(${(g.docs || []).join(' · ')})를 다시 훑어 다음을 찾고 **그 파일을 직접 고친다**(줄 추가·수정만, 다른 파일 금지):`,
  `1) 근거 문서에 있는 사용자 행동인데 TC 가 없는 것(특히 예외·오류·권한·빈 상태·뒤로가기) → 새 TC(같은 id 규칙, 이어지는 번호).`,
  `2) 기대문이 관찰 불가능한 말(「정상 동작」「적절히」)이거나 근거 문서와 다른 것 → 근거 문서 원문으로 고친다.`,
  `3) 절차가 화면 문구가 아닌 내부 이름(위젯·함수 이름)으로 적힌 것 → 화면에 보이는 문구로.`,
  `4) 등급이 기준(1 = 출시 필수 핵심 여정·보안·데이터 정합)과 어긋나는 것.`,
  `5) 비밀 값처럼 보이는 문자열 → 별칭으로.`,
  `반환: added(새 TC 수) · fixed(고친 TC 수) · gaps_left(못 메운 공백 — 근거 문서 자체가 없는 등) · notes.`,
].join('\n')

const results = await pipeline(
  A.groups || [],
  g => agent(draftPrompt(g), opt(`draft:${g.name}`, 'Draft', DRAFT)),
  (d, g) => (A.critique === false ? d : agent(critPrompt(g, d), opt(`critique:${g.name}`, 'Critique', CRIT)).then(c => ({ ...d, critique: c }))),
)
const dead = (A.groups || []).filter((g, i) => !results[i])
if (dead.length) log(`⚠️ 죽은 묶음: ${dead.map(g => g.name).join(', ')} — 그 묶음만 새 run 으로 다시`)
return { groups: results }
