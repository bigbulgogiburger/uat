#!/usr/bin/env python
"""회차 실행 폴더를 만든다 — run.json · 하위 폴더 · (2차부터) 지난 회차 이어받기.

  python init_run.py --round 1 --build <sha> [--date YYYY-MM-DD] [--name <폴더명>] [--title "…"]
  python init_run.py --round 3 --build <sha> --prev <2차 RUN 폴더>

- 폴더 위치: 프로필의 runs_dir(없으면 현재 폴더) / <date>-uat<round>.
- --prev 가 있으면 tc.jsonl · defects.json · tc-brief.md · checklist-head.md · lanes/notes-*.md 를 복사하고,
  지난 회차의 판정(out/*.jsonl)을 out/r<회차>-<이름>.jsonl 로 보존한다(이미 r<N>- 접두가 있는 파일은 그대로).
  work/ 의 상태 파일(프로필 carry_work — 기본 requests.jsonl · db-writes.log · state-snapshots.json)도 이어받는다.
  지난 changes.md 는 lanes/changes.prev.md 로 둔다 — 새 changes.md 는 그 위에 이번 회차 변경을 얹어 쓴다.
- 이미 있는 폴더에는 덮어쓰지 않는다(판정이 섞이면 새 P 가 옛 F 에 진다).
"""
import argparse
import datetime
import glob
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uatlib as U  # noqa: E402


def main():
    U.utf8_stdout()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--round', type=int, required=True)
    p.add_argument('--build', required=True, help='이번 회차가 재는 커밋 sha(서버·클라이언트 공통)')
    p.add_argument('--date', default=datetime.date.today().isoformat())
    p.add_argument('--name')
    p.add_argument('--title')
    p.add_argument('--prev', help='직전 회차 실행 폴더')
    p.add_argument('--config')
    p.add_argument('--runs-dir')
    a = p.parse_args()

    cfg_path = U.config_path(None, a.config)
    cfg = U.load_config(None, a.config)
    runs_dir = U.expand(a.runs_dir or cfg.get('runs_dir') or os.getcwd())
    name = a.name or f'{a.date}-uat{a.round}'
    run = os.path.join(runs_dir, name)
    if os.path.exists(os.path.join(run, 'run.json')):
        raise SystemExit(f'이미 있다: {run} — 다른 --name 을 쓰거나 그 폴더를 이어서 쓸 것(새로 만들지 않는다)')
    for sub in ('lanes', 'out', 'shots', 'work', 'tc-draft'):
        os.makedirs(os.path.join(run, sub), exist_ok=True)

    info = {
        'round': a.round,
        'build': a.build,
        'date': a.date,
        'title': a.title or f'{cfg.get("project", "project")} UAT {a.round}차 ({a.date})',
        'config': cfg_path,
        'prev': U.expand(a.prev) if a.prev else None,
        'created_at': U.now(),
    }
    carried = []
    if a.prev:
        prev = U.expand(a.prev)
        prev_info = U.load_run(prev)
        prev_round = prev_info.get('round') or (a.round - 1)
        for fn in ('tc.jsonl', 'defects.json', 'tc-brief.md', 'checklist-head.md'):
            src = os.path.join(prev, fn)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(run, fn))
                carried.append(fn)
        for src in glob.glob(os.path.join(prev, 'lanes', 'notes-*.md')) + glob.glob(os.path.join(prev, 'lanes', 'recheck.md')):
            dst_name = os.path.basename(src) if 'notes-' in src else 'recheck.prev.md'
            shutil.copy2(src, os.path.join(run, 'lanes', dst_name))
            carried.append('lanes/' + dst_name)
        ch = os.path.join(prev, 'lanes', 'changes.md')
        if os.path.exists(ch):
            shutil.copy2(ch, os.path.join(run, 'lanes', 'changes.prev.md'))
            carried.append('lanes/changes.prev.md')
        n_out = 0
        for src in glob.glob(os.path.join(prev, 'out', '*.jsonl')):
            base = os.path.basename(src)
            dst = base if U.round_of_file(base) is not None else f'r{prev_round}-{base}'
            shutil.copy2(src, os.path.join(run, 'out', dst))
            n_out += 1
        carried.append(f'out/*.jsonl {n_out}개(r<N>- 로 보존)')
        for fn in cfg.get('carry_work') or []:
            src = os.path.join(prev, 'work', fn)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(run, 'work', fn))
                carried.append('work/' + fn)
    U.write_json(os.path.join(run, 'run.json'), info)
    print('run', run.replace('\\', '/'))
    print('build', a.build, '· round', a.round, '· config', cfg_path or '(없음 — 기본값)')
    if carried:
        print('carried', ' · '.join(carried))
    r = run.replace('\\', '/')
    print(f'다음(bash): export UAT_RUN={r}')
    print(f"다음(PowerShell): $env:UAT_RUN='{r}'")


if __name__ == '__main__':
    main()
