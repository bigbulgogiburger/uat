#!/usr/bin/env python
"""회차 판정 분류 — 결함이 고쳐졌나 · 재발했나 · 새 결함 후보 · 부수 · BLOCKED · 등급1 잔여.

  python triage.py [--run RUN] [--json RUN/triage.json]

- 이번 회차 기록 = out/ 의 r<N>- 접두가 아닌 파일. TC 판정은 회차를 통틀어 가장 나중 기록이 이긴다.
- 결함(status open·qa·reopened)마다 관련 TC 의 이번 회차 판정을 본다:
  전부 P → 「fixed 후보」 · 하나라도 F → 「재발(F)」 · 관련 TC 가 없음(부수 결함) → 「미확인 — 재확인 레인 필요」 ·
  이번 회차 기록 없음 → 「미확인(이번 회차 기록 없음)」 · 그 밖(P+BLOCKED 등) → 「판정 보류」.
- 새 결함 후보 = 이번 회차 F 인데 어느 결함의 tcs 에도 없는 TC + 이번 회차 부수 기록.
이 출력은 **후보**다. fixed 로 바꾸기 전에 증거를 보고, 재발이면 같은 원인인지 코드로 확인한다(references/judgment.md §4).
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uatlib as U  # noqa: E402


def classify(real, cur):
    vs = {t: (cur.get(t) or {}).get('v') for t in real}
    if not real:
        return '미확인 — 재확인 레인 필요', vs
    if all(v == 'P' for v in vs.values()):
        return 'fixed 후보', vs
    if any(v == 'F' for v in vs.values()):
        return '재발 후보(F — 같은 증상인지 actual 대조)', vs
    if all(v is None for v in vs.values()):
        return '미확인(이번 회차 기록 없음)', vs
    return '판정 보류(' + ','.join(f'{t}={v}' for t, v in vs.items()) + ')', vs


def main():
    U.utf8_stdout()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--run')
    p.add_argument('--config')
    p.add_argument('--json')
    p.add_argument('--width', type=int, default=170)
    a = p.parse_args()
    run = U.find_run(a.run)
    W = a.width
    tcs = U.load_tcs(run)
    latest, cur, _, sides_cur = U.load_verdicts(run)
    defects = U.load_defects(run)
    why_p = os.path.join(run, 'lanes', 'manifest.json')
    selected = None
    if os.path.exists(why_p):
        man = json.load(open(why_p, encoding='utf-8'))
        selected = [tid for kind in ('api', 'ui') for e in man.get(kind, []) for tid in e.get('ids', [])]

    c = collections.Counter(r['v'] for r in cur.values())
    head = f'이번 회차 측정 {len(cur)}' + (f'/{len(selected)}' if selected else '') + ' TC — ' + ' · '.join(f'{k} {v}' for k, v in sorted(c.items()))
    print(head)
    missing = [t for t in (selected or []) if t not in cur]
    if missing:
        print('  배정됐는데 이번 회차 기록 없음:', ' '.join(missing))

    print('\n## 결함 재확인(open · qa · reopened)')
    in_defect, res = set(), []
    for d in sorted(defects, key=lambda d: (U.SEV_ORDER.get(d.get('sev'), 3), d.get('id', ''))):
        real = [t for t in (d.get('tcs') or []) if t in tcs]
        in_defect.update(real)
        if d.get('status') not in U.OPEN_STATUSES:
            continue
        verdict, vs = classify(real, cur)
        res.append({'id': d['id'], 'sev': d.get('sev'), 'tracker': d.get('jira') or d.get('tracker'), 'status': d.get('status'),
                    'verdict': verdict, 'vs': vs})
        print(f"  {d['id']:9} {str(d.get('sev')):8} {str(d.get('jira') or d.get('tracker')):11} {str(d.get('status')):8} {verdict:24} "
              + ' '.join(f'{t}={v}' for t, v in vs.items()))

    new_f = sorted((r for t, r in cur.items() if r['v'] == 'F' and t not in in_defect),
                   key=lambda r: (U.SEV_ORDER.get(r.get('sev'), 3), r['tc']))
    print('\n## 이번 회차 F — 새 결함 후보(어느 결함에도 없는 TC)')
    for r in new_f:
        print(f"  {r['tc']:6} {str(r.get('sev')):8} {r.get('lane', ''):10} {(r.get('actual') or '')[:W]}")
    print('\n## 이번 회차 F — 기존 결함 TC 의 F(같은 결함의 재발인지, 같은 TC 의 다른 결함인지 actual·note 로 가른다)')
    for r in sorted((r for t, r in cur.items() if r['v'] == 'F' and t in in_defect), key=lambda r: r['tc']):
        print(f"  {r['tc']:6} {str(r.get('sev')):8} {(r.get('actual') or '')[:W]}" + (f"  [note] {r['note'][:80]}" if r.get('note') else ''))
    print(f'\n## 이번 회차 부수 기록 {len(sides_cur)}건')
    for s in sorted(sides_cur, key=lambda s: U.SEV_ORDER.get(s.get('sev'), 3)):
        print(f"  {str(s.get('sev')):8} {s.get('lane', ''):10} {(s.get('title') or '')[:W]}")
    blocked = [(t, r) for t, r in cur.items() if r['v'] == 'BLOCKED']
    print(f'\n## 이번 회차 BLOCKED {len(blocked)}건')
    for t, r in blocked:
        g = (tcs.get(t) or {}).get('grade', '?')
        print(f"  {t:6} g{g} {(r.get('actual') or '')[:W]}")
    g1 = [t for t, x in tcs.items() if int(x.get('grade', 9)) == 1 and (latest.get(t) or {}).get('v') not in ('P', 'NA')]
    print(f'\n## 등급1 중 P·NA 아닌 것 {len(g1)}건(이번 회차 기록이 없으면 지난 회차 판정 — 회차 시작 직후엔 지난 회차 잔여다):', ' '.join(f"{t}={(latest.get(t) or {}).get('v')}" for t in g1))
    fixed_claims = sorted({t for t, r in cur.items() if r.get('fix') == '해소'})
    if fixed_claims:
        print('\n레인이 「해소」로 적은 TC:', ' '.join(fixed_claims))
    if a.json:
        U.write_json(a.json, {
            'counts': dict(c), 'missing': missing, 'defects': res,
            'new_f': [{k: r.get(k) for k in ('tc', 'sev', 'lane', 'actual', 'repro', 'evidence', 'at')} for r in new_f],
            'sides': sides_cur, 'blocked': [{'tc': t, 'actual': r.get('actual')} for t, r in blocked], 'g1_bad': g1,
        })
        print('wrote', a.json)


if __name__ == '__main__':
    main()
