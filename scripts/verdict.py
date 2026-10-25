#!/usr/bin/env python
"""판정 1건 기록 — RUN/out/<lane>.jsonl 에 한 줄을 더한다(필수 필드·비밀 패턴 검사).

  python verdict.py --lane intake --tc D-03 --v P --evidence "shots/d03-brand.s.png" [--actual "…"]
  python verdict.py --lane intake --tc D-07 --v F --sev Major --actual "…" --evidence "…" --repro "1) … 2) …"
  python verdict.py --lane intake --tc D-40 --v BLOCKED --actual "사유 — 시도한 것"
  python verdict.py --lane intake --side --area D --sev Minor --title "…" --actual "…" --evidence "…" --repro "…" --note "D-12 하다가 봄"
  python verdict.py --summary --lane intake            레인 집계(같은 레인의 모든 묶음)

규칙
- P 도 증거(--evidence: 스크린샷 경로나 API 응답 요지)가 필수다. 증거 없는 P 는 「안 해 봤다」와 구별되지 않는다.
- F 와 부수 결함은 --sev(Critical|Major|Minor) · --actual · --evidence · --repro 필수. repro 는 남이 그대로 밟을 수 있게.
- BLOCKED 는 --actual 에 사유 필수. 기대문이 의심스러우면 F 가 아니라 BLOCKED + 「기대문 의심 — 이유」.
- 비밀 값(테스트 계정 번호·인증번호·토큰)처럼 보이는 문자열이 있으면 기록을 거부한다. 별칭(계정#1)으로 쓴다.
- --fix 해소|미해소|부분 : 지난 회차 결함의 재측정이면 그 결과를 함께 남긴다(선택).
같은 TC 를 여러 번 기록하면 가장 나중 기록이 이긴다(재확인이 덮는다).
"""
import argparse
import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uatlib as U  # noqa: E402

SEVS = ('Critical', 'Major', 'Minor')


def summary(run, lane):
    rows = []
    for fn in glob.glob(os.path.join(run, 'out', '*.jsonl')):
        if U.round_of_file(fn) is not None:
            continue
        rows += [r for r in U.read_jsonl(fn) if r.get('lane') == lane]
    last, sides = {}, 0
    for r in sorted(rows, key=lambda r: r.get('at', '')):
        if r.get('side'):
            sides += 1
        else:
            last[r['tc']] = r
    c = collections.Counter(r['v'] for r in last.values())
    sev = collections.Counter(r['sev'] for r in list(last.values()) + [r for r in rows if r.get('side')] if r.get('sev'))
    print(json.dumps({'lane': lane, 'tcs': len(last), 'verdicts': dict(c), 'side_findings': sides,
                      'severity': dict(sev), 'judged': sorted(last)}, ensure_ascii=False))


def main():
    U.utf8_stdout()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--run')
    p.add_argument('--config')
    p.add_argument('--lane', required=True)
    p.add_argument('--tc')
    p.add_argument('--v', choices=['P', 'F', 'NA', 'BLOCKED'])
    p.add_argument('--sev', choices=SEVS)
    p.add_argument('--actual', default='')
    p.add_argument('--evidence', default='')
    p.add_argument('--repro', default='')
    p.add_argument('--note', default='')
    p.add_argument('--fix', choices=['해소', '미해소', '부분'])
    p.add_argument('--side', action='store_true')
    p.add_argument('--area')
    p.add_argument('--title')
    p.add_argument('--summary', action='store_true')
    a = p.parse_args()
    run = U.find_run(a.run)
    cfg = U.load_config(run, a.config)
    if a.summary:
        return summary(run, a.lane)

    for f in ('actual', 'evidence', 'repro', 'note', 'title'):
        hit = U.find_secret_like(getattr(a, f) or '', cfg)
        if hit:
            raise SystemExit(f'--{f} 에 비밀처럼 보이는 값({hit})이 있다 — 별칭으로 바꾸고 다시 기록할 것')
    rec = {'at': U.now(), 'lane': a.lane}
    if a.side:
        if not (a.area and a.title and a.sev and a.actual and a.evidence and a.repro):
            raise SystemExit('--side 는 --area --title --sev --actual --evidence --repro 필수')
        rec.update({'side': True, 'area': a.area, 'title': a.title, 'sev': a.sev, 'actual': a.actual,
                    'evidence': a.evidence, 'repro': a.repro, 'note': a.note})
    else:
        if not (a.tc and a.v):
            raise SystemExit('--tc 와 --v 필수')
        tcs = U.load_tcs(run)
        if tcs and a.tc not in tcs:
            raise SystemExit(f'{a.tc} 는 tc.jsonl 에 없다 — TC 밖에서 본 결함이면 --side 로 기록할 것')
        if a.v == 'F' and not (a.sev and a.actual and a.evidence and a.repro):
            raise SystemExit('F 는 --sev --actual --evidence --repro 필수')
        if a.v == 'BLOCKED' and not a.actual:
            raise SystemExit('BLOCKED 는 --actual 에 사유 필수(무엇을 시도했는지 포함)')
        if a.v == 'P' and not a.evidence:
            raise SystemExit('P 도 --evidence(스크린샷 경로나 API 응답 요지) 필수')
        if a.v != 'F' and a.sev:
            raise SystemExit('--sev 는 F 에만 붙인다')
        rec.update({'tc': a.tc, 'v': a.v, 'sev': a.sev, 'actual': a.actual, 'evidence': a.evidence,
                    'repro': a.repro, 'note': a.note})
        if a.fix:
            rec['fix'] = a.fix
    U.append_jsonl(os.path.join(run, 'out', f'{a.lane}.jsonl'), rec)
    print('recorded', rec.get('tc') or ('side:' + rec['title'][:40]), rec.get('v', ''), rec.get('sev') or '')


if __name__ == '__main__':
    main()
