#!/usr/bin/env python
"""TC 초안(RUN/tc-draft/*.jsonl)을 병합·검증해 RUN/tc.jsonl 을 쓴다.

  python tc_merge.py [--run RUN] [--check]      --check = 쓰지 않고 검사만
  python tc_merge.py --check --input RUN/tc.jsonl   이미 병합된(또는 손으로 고친) tc.jsonl 만 검사 — 2차부터 기대문을 정정한 뒤에

검사: 필수 필드 · id 중복 · id 접두와 area 일치 · area 가 프로필 areas 에 있는가 · grade 1~3 ·
method 가 프로필 methods 안 · feasibility(ok|data|blocked) · blocked/data 인데 사유·준비 방법이 빔 · source 가 빔.
문제가 있으면 PROBLEM 줄을 찍고 종료 코드 1(--check 가 아니어도 쓰기는 한다 — 사람이 고쳐서 다시 돌린다).
"""
import argparse
import collections
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uatlib as U  # noqa: E402

REQUIRED = ('id', 'area', 'grade', 'title', 'steps', 'expected', 'method', 'feasibility', 'source')
FEAS = ('ok', 'data', 'blocked')


def main():
    U.utf8_stdout()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--run')
    p.add_argument('--config')
    p.add_argument('--check', action='store_true')
    p.add_argument('--input', action='append', help='tc-draft 대신 검사할 jsonl(여러 번) — --check 와 함께')
    a = p.parse_args()
    run = U.find_run(a.run)
    cfg = U.load_config(run, a.config)
    areas = U.area_order(cfg)
    methods = set(cfg.get('methods') or [])

    tcs, seen, problems = [], set(), []
    files = [U.expand(x) for x in a.input] if a.input else sorted(glob.glob(os.path.join(run, 'tc-draft', '*.jsonl')))
    if a.input and not a.check:
        raise SystemExit('--input 은 --check 와 함께 쓴다(병합 결과를 덮어쓰지 않게)')
    if not files:
        raise SystemExit('tc-draft/*.jsonl 이 없다 — 병합된 tc.jsonl 을 검사하려면 --check --input RUN/tc.jsonl')
    for fn in files:
        name = os.path.basename(fn)
        for ln, t in enumerate(U.read_jsonl(fn), 1):
            where = f'{name}:{ln} {t.get("id")}'
            miss = [k for k in REQUIRED if t.get(k) in (None, '', [])]
            if miss:
                problems.append(f'{where} 필수 필드 없음 {miss}')
            tid = str(t.get('id') or '')
            if tid in seen:
                problems.append(f'{where} id 중복 — 건너뜀')
                continue
            seen.add(tid)
            area = t.get('area')
            if areas and area not in areas:
                problems.append(f'{where} area {area!r} 가 프로필 areas 에 없다')
            if area and not tid.startswith(f'{area}-'):
                problems.append(f'{where} id 접두가 area 와 다르다')
            try:
                t['grade'] = int(t.get('grade'))
                if t['grade'] not in (1, 2, 3):
                    raise ValueError
            except (TypeError, ValueError):
                problems.append(f'{where} grade 는 1·2·3')
            if methods and t.get('method') not in methods:
                problems.append(f'{where} method {t.get("method")!r} 가 프로필 methods 밖')
            if t.get('feasibility') not in FEAS:
                problems.append(f'{where} feasibility 는 ok|data|blocked')
            if t.get('feasibility') == 'blocked' and not t.get('feasibility_note'):
                problems.append(f'{where} blocked 인데 feasibility_note(사유)가 빔')
            if t.get('feasibility') == 'data' and not t.get('data_setup'):
                problems.append(f'{where} data 인데 data_setup(준비 방법)이 빔')
            if re.search(r'정상\s*(동작|작동)', str(t.get('expected') or '')):
                problems.append(f'{where} expected 에 「정상 동작」 — 관찰 가능한 결과로 쓸 것')
            leak = U.find_secret_like(' '.join(str(v) for v in t.values() if v), cfg)  # 모든 필드 — title·source 도 문서로 나간다
            if leak:
                problems.append(f'{where} 비밀처럼 보이는 값({leak}) — 별칭으로 바꿀 것')
            tcs.append(t)

    def key(t):
        ai = areas.index(t['area']) if t.get('area') in areas else len(areas)
        num = re.sub(r'\D', '', str(t.get('id')).split('-', 1)[-1]) or '0'
        return (ai, t.get('area') or '', int(num))

    tcs.sort(key=key)
    if not a.check:
        U.write_jsonl(os.path.join(run, 'tc.jsonl'), tcs)
        print('wrote', os.path.join(run, 'tc.jsonl').replace('\\', '/'))
    c = collections.Counter
    print('TC', len(tcs), dict(sorted(c(t.get('area') for t in tcs).items(), key=lambda kv: areas.index(kv[0]) if kv[0] in areas else 99)))
    print('grade', dict(sorted(c(t.get('grade') for t in tcs).items())), '· method', dict(c(t.get('method') for t in tcs)))
    print('feasibility', dict(c(t.get('feasibility') for t in tcs)), '· impl', dict(c(t.get('impl') or '-' for t in tcs)))
    no_source_note = sum(1 for t in tcs if '근거 미확인' in str(t.get('notes') or ''))
    if no_source_note:
        print(f'근거 미확인 TC {no_source_note}건 — 판정 전에 사람이 근거를 정하거나 기대문 의심으로 다룬다')
    for pr in problems:
        print('PROBLEM', pr)
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
