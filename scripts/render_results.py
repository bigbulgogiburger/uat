#!/usr/bin/env python
"""판정(out/*.jsonl) + 확정 결함(defects.json) → 결과보고 문서의 회차 절.

  python render_results.py --round 3 --date 2026-10-25 --build <sha> --out <repo>/docs/UAT_결과보고.md [--note "…"]…
  python render_results.py --stats                       집계만(JSON) — 문서를 쓰지 않는다

- TC 판정은 회차를 가로질러 **가장 나중 기록**이 이긴다(이 문서는 「지금 상태」를 보여 준다).
  이번 회차에 실제로 잰 수는 --note 로 머리에 적는다(예: "실측 117 TC — P 99 · F 6 · BLOCKED 12").
- GO = 미해결 확정 결함(open·qa·reopened) Critical 0 · Major 0, 그리고 등급1 이 전부 P·NA(·수용된 보류 결함).
  defects.json 이 없으면 F 를 그대로 결함 후보로 보인다(감사 전 표시).
- 문서에 같은 회차 절이 있으면 그 절만 갈아 끼운다(다른 회차 절은 보존). 회차 절은 문서 끝에 순서대로 붙는다.
"""
import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uatlib as U  # noqa: E402

V_LABEL = {'P': 'P', 'F': 'F', 'NA': 'N/A', 'BLOCKED': 'BLOCKED'}
STATUS_NOTE = '> 상태: open 미수정 · qa 수정 반영(재측정 전) · fixed 재측정 통과 · reopened 재발(새 결함으로 이어짐) · accepted 수용된 보류 · dup 중복'


def stats(tcs, latest, defects):
    c = collections.Counter((latest.get(tid) or {}).get('v', '미측정') for tid in tcs)
    sev = collections.Counter()
    for d in defects or []:
        if d.get('status') in U.OPEN_STATUSES:
            sev[d['sev']] += 1
    # 감사되지 않은 F — 지금 F 인데 그 TC 를 맡은 미해결·수용 결함이 없다. 결함 목록에 아직 안 올렸다고
    # GO 가 나오면 안 된다(감사 누락이 곧 출시 판정 누락이 된다). 레인이 단 심각도로 센다.
    covered = {t for d in defects or [] if d.get('status') in U.OPEN_STATUSES + ('accepted',) for t in d.get('tcs') or []}
    unaudited = sorted(tid for tid, r in latest.items() if tid in tcs and r.get('v') == 'F' and tid not in covered)
    for tid in unaudited:
        sev[latest[tid].get('sev')] += 1
    accepted_tcs = {t for d in defects or [] if d.get('status') == 'accepted' for t in d.get('tcs') or []}
    g1_bad = [tid for tid, t in tcs.items() if int(t.get('grade', 9)) == 1
              and (latest.get(tid) or {}).get('v') not in ('P', 'NA') and tid not in accepted_tcs]
    go = sev.get('Critical', 0) == 0 and sev.get('Major', 0) == 0 and not g1_bad
    return c, sev, g1_bad, go, unaudited


def section(cfg, rnd, date, build, tcs, latest, sides, defects, notes):
    names = cfg.get('areas') or {}
    c, sev, g1_bad, go, unaudited = stats(tcs, latest, defects)
    out = [f'## {rnd}차 측정 ({date})', '',
           f'- 빌드: {build}',
           f'- 판정: **{"GO" if go else "NO-GO"}** — 미해결 결함(확정 + 감사 전 F) Critical {sev.get("Critical", 0)} · Major {sev.get("Major", 0)} · Minor {sev.get("Minor", 0)} · 등급1 미통과 {len(g1_bad)}',
           f'- TC {len(tcs)}건 현재 상태: P {c["P"]} · F {c["F"]} · N/A {c["NA"]} · BLOCKED {c["BLOCKED"]} · 미측정 {c["미측정"]}']
    if defects and unaudited:
        out.append(f'- ⚠️ 감사 전 F {len(unaudited)}건(결함 목록에 없음 — 레인 심각도로 셈): {", ".join(unaudited)}')
    out += [f'- {n}' for n in notes] + ['']

    out += ['### 확정 결함', '']
    if not defects:
        out += ['> 감사 전 — F 판정을 그대로 결함 후보로 보인다.', '', '| TC | 심각도 | 영역 | 실제 결과 |', '|---|---|---|---|']
        for r in sorted((r for r in latest.values() if r['v'] == 'F'), key=lambda r: (U.SEV_ORDER.get(r.get('sev'), 3), r['tc'])):
            out.append(f"| {r['tc']} | {r.get('sev')} | {(tcs.get(r['tc']) or {}).get('area', '')} | {U.esc_md(r.get('actual'))[:200]} |")
    else:
        out += [STATUS_NOTE, '', '| ID | 심각도 | 영역 | 결함 | 관련 TC | 트래커 | 상태 |', '|---|---|---|---|---|---|---|']
        for d in sorted(defects, key=lambda d: (U.SEV_ORDER.get(d.get('sev'), 3), d['id'])):
            out.append(f"| {d['id']} | {d.get('sev')} | {U.esc_md(d.get('area', ''))} | {U.esc_md(d.get('title'))} | "
                       f"{U.esc_md(', '.join(d.get('tcs') or []))} | {d.get('tracker') or d.get('jira') or '-'} | {d.get('status', 'open')} |")
    out.append('')

    out += ['### 영역별 현재 상태', '', '| 영역 | 이름 | TC | P | F | N/A | BLOCKED | 미측정 |', '|---|---|---:|---:|---:|---:|---:|---:|']
    order = list(names) + sorted({t['area'] for t in tcs.values()} - set(names))
    for k in order:
        ids = [tid for tid, t in tcs.items() if t['area'] == k]
        if not ids:
            continue
        cc = collections.Counter((latest.get(tid) or {}).get('v', '미측정') for tid in ids)
        out.append(f"| {k} | {names.get(k, '')} | {len(ids)} | {cc['P']} | {cc['F']} | {cc['NA']} | {cc['BLOCKED']} | {cc['미측정']} |")
    out.append('')

    out += ['### 등급1 중 P·N/A 가 아닌 것', '']
    if g1_bad:
        out += ['| TC | 판정 | 항목 | 사유 |', '|---|---|---|---|']
        for tid in g1_bad:
            r = latest.get(tid) or {}
            out.append(f"| {tid} | {V_LABEL.get(r.get('v'), '미측정')} | {U.esc_md(tcs[tid]['title'])[:70]} | {U.esc_md(r.get('actual'))[:160]} |")
    else:
        out.append('없음.')
    out.append('')

    bl = [(tid, latest[tid]) for tid in tcs if (latest.get(tid) or {}).get('v') == 'BLOCKED']
    out += [f'### BLOCKED ({len(bl)}건)', '']
    if bl:
        out += ['| TC | 등급 | 사유 |', '|---|:-:|---|']
        for tid, r in bl:
            out.append(f"| {tid} | {tcs[tid]['grade']} | {U.esc_md(r.get('actual'))[:220]} |")
    out.append('')

    if sides:
        out += [f'### TC 밖에서 본 결함 ({len(sides)}건 — 재확인 전 기록 포함)', '', '| 레인 | 심각도 | 영역 | 결함 |', '|---|---|---|---|']
        for s in sorted(sides, key=lambda s: U.SEV_ORDER.get(s.get('sev'), 3)):
            out.append(f"| {s.get('lane', '')} | {s.get('sev')} | {s.get('area', '')} | {U.esc_md(s.get('title'))} |")
        out.append('')

    if defects:
        out += ['### 결함 상세', '']
        for d in sorted(defects, key=lambda d: (U.SEV_ORDER.get(d.get('sev'), 3), d['id'])):
            out += [f"#### {d['id']} · {d.get('sev')} · {d.get('title')}",
                    f"- 관련 TC: {', '.join(d.get('tcs') or []) or '-'} · 트래커: {d.get('tracker') or d.get('jira') or '-'} · 상태: {d.get('status', 'open')}"
                    + (f" → {d['reopened_as']}" if d.get('reopened_as') else ''),
                    f"- 현상: {d.get('summary', '')}"]
            if d.get('cause'):
                out.append(f"- 원인: {d['cause']}")
            ev = d.get('evidence', '')
            out += [f"- 재현: {d.get('repro', '')}", f"- 증거: {' · '.join(ev) if isinstance(ev, list) else ev}", '']

    out += ['<details><summary>TC 별 현재 판정 전체</summary>', '', '| TC | 등급 | 판정 | 심각도 | 레인 | 근거·실제 |', '|---|:-:|---|---|---|---|']
    for tid, t in tcs.items():
        r = latest.get(tid) or {}
        body = r.get('actual') if r.get('v') != 'P' else (r.get('evidence') or r.get('actual'))
        out.append(f"| {tid} | {t['grade']} | {V_LABEL.get(r.get('v'), '미측정')} | {r.get('sev') or ''} | {r.get('lane', '')} | {U.esc_md(body)[:160]} |")
    out += ['', '</details>', '']
    return '\n'.join(out), go, c, sev


def main():
    U.utf8_stdout()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--run')
    p.add_argument('--config')
    p.add_argument('--round', type=int)
    p.add_argument('--date')
    p.add_argument('--build')
    p.add_argument('--out')
    p.add_argument('--title')
    p.add_argument('--stats', action='store_true')
    p.add_argument('--note', action='append', default=[])
    a = p.parse_args()
    run = U.find_run(a.run)
    cfg = U.load_config(run, a.config)
    info = U.load_run(run)
    tcs = U.load_tcs(run)
    latest, cur, sides_all, sides_cur = U.load_verdicts(run)
    defects = U.load_defects(run)
    if a.stats:
        c, sev, g1_bad, go, unaudited = stats(tcs, latest, defects)
        cc = collections.Counter(r['v'] for r in cur.values())
        print(json.dumps({'tc': len(tcs), 'now': dict(c), 'this_round': dict(cc), 'open_severity': dict(sev),
                          'g1_bad': g1_bad, 'unaudited_f': unaudited, 'sides_this_round': len(sides_cur), 'go': go}, ensure_ascii=False))
        return
    if not a.out:
        raise SystemExit('--out 필요(또는 --stats)')
    rnd = a.round or info.get('round')
    body, go, c, sev = section(cfg, rnd, a.date or info.get('date'), a.build or info.get('build'), tcs, latest,
                               sides_cur, defects, a.note)
    title = a.title or f"{cfg.get('project', '')} UAT 결과 보고".strip()
    head = (f'# {title}\n\n> 판정 원본: UAT 실행 폴더 `out/*.jsonl` · 결함 원본: `defects.json`\n'
            '> 합격(GO) 기준: 미해결 확정 결함 Critical 0 · Major 0, 등급1 TC 전부 P · N/A · 수용된 보류.\n\n')
    doc = open(a.out, encoding='utf-8').read() if os.path.exists(a.out) else head
    pat = re.compile(rf'^## {rnd}차 측정 .*?(?=^## \d+차 측정 |\Z)', re.S | re.M)
    doc = pat.sub(lambda m: body.rstrip() + '\n\n', doc) if pat.search(doc) else doc.rstrip() + '\n\n' + body
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, 'w', encoding='utf-8', newline='\n').write(doc.rstrip() + '\n')
    print('wrote', a.out, 'GO' if go else 'NO-GO', dict(c), dict(sev))


if __name__ == '__main__':
    main()
