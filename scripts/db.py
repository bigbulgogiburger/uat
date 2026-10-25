#!/usr/bin/env python
"""UAT DB 러너 — 읽기는 자유, 쓰기는 이유·원복 SQL 과 함께 기록하고 되돌릴 수 있게 한다.

  python db.py q "SELECT …" [--max 4000]
  python db.py w "UPDATE … WHERE …" --why "<TC> 데이터 준비" --revert "UPDATE … WHERE …" [--lane L] --yes
  python db.py w "INSERT …" --why "…" --no-revert "다음 회차 시드로 지움" --yes      (원복 SQL 을 못 쓰는 경우 — 이유 필수)
  python db.py log                      쓰기 기록(RUN/work/db-writes.log, JSON 한 줄씩)
  python db.py revert [--id N | --all] [--dry]      아직 되돌리지 않은 쓰기를 역순으로 원복

프로필 db 예:
  "db": {"read":  ["mysql", "--defaults-extra-file=~/.uat-secrets/shop/my.cnf", "-N", "-B", "-e", "{sql}", "shop_dev"],
         "write": ["mysql", "--defaults-extra-file=~/.uat-secrets/shop/my.cnf", "-e", "{sql}", "shop_dev"],
         "write_guard": "UAT"}
- 명령은 인자 배열이다(셸을 거치지 않는다). {sql} 자리에 SQL 이 들어간다. 접속 비밀은 명령이 가리키는 파일에만 둔다.
- write_guard(선택): 쓰기 SQL 에 이 문자열(예: 데이터 접두어)이나 --target-ok 가 없으면 거부한다 — UAT 가 만든 행에만 쓰게 하는 장치.
- DROP · TRUNCATE · ALTER · GRANT 는 언제나 거부한다. WHERE 없는 UPDATE·DELETE 도 거부한다.
출력은 비밀 패턴으로 가린다.
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uatlib as U  # noqa: E402

FORBIDDEN = re.compile(r'^\s*(DROP|TRUNCATE|ALTER|GRANT|REVOKE|CREATE\s+USER)\b', re.I)


def cmd_of(cfg, kind, sql):
    tpl = (cfg.get('db') or {}).get(kind)
    if not tpl:
        raise SystemExit(f'프로필 db.{kind} 가 없다')
    home = os.path.expanduser('~').replace('\\', '/')
    # 「~/…」와 「--opt=~/…」의 ~ 만 홈으로 바꾼다. SQL 안의 ~ 는 건드리지 않는다.
    return [sql if x == '{sql}' else re.sub(r'(^|=)~(?=/)', lambda m: m.group(1) + home, x).replace('{sql}', sql) for x in tpl]


def run_sql(cfg, kind, sql):
    r = subprocess.run(cmd_of(cfg, kind, sql), capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.returncode, r.stdout, r.stderr


def log_path(run):
    return os.path.join(run, 'work', 'db-writes.log')


def read_log(run):
    rows = []
    p = log_path(run)
    if os.path.exists(p):
        for line in open(p, encoding='utf-8'):
            line = line.strip()
            if line.startswith('{'):
                rows.append(json.loads(line))
    return rows


def check_write(cfg, sql, target_ok):
    for stmt in [s for s in sql.split(';') if s.strip()]:
        if FORBIDDEN.match(stmt):
            raise SystemExit('DDL·권한 문은 이 도구로 쓰지 않는다')
        if re.match(r'^\s*(UPDATE|DELETE)\b', stmt, re.I) and not re.search(r'\bWHERE\b', stmt, re.I):
            raise SystemExit('WHERE 없는 UPDATE·DELETE 는 거부한다')
    guard = (cfg.get('db') or {}).get('write_guard')
    if guard and guard not in sql and not target_ok:
        raise SystemExit(f'쓰기 SQL 에 「{guard}」가 없다 — UAT 가 만든 행만 대상으로 하거나, 확인했으면 --target-ok')


def main():
    U.utf8_stdout()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('cmd', choices=['q', 'w', 'log', 'revert'])
    p.add_argument('sql', nargs='?')
    p.add_argument('--run')
    p.add_argument('--config')
    p.add_argument('--why')
    p.add_argument('--revert')
    p.add_argument('--no-revert')
    p.add_argument('--lane', default='')
    p.add_argument('--yes', action='store_true')
    p.add_argument('--target-ok', action='store_true')
    p.add_argument('--id', type=int)
    p.add_argument('--all', action='store_true')
    p.add_argument('--dry', action='store_true')
    p.add_argument('--max', type=int, default=4000)
    a = p.parse_args()
    run = U.find_run(a.run)
    cfg = U.load_config(run, a.config)

    if a.cmd == 'q':
        if not a.sql or not re.match(r'^\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN|WITH)\b', a.sql, re.I):
            raise SystemExit('q 는 읽기 문(SELECT·SHOW·DESCRIBE·EXPLAIN·WITH)만')
        rc, out, err = run_sql(cfg, 'read', a.sql)
        text = U.mask(out if rc == 0 else err, cfg)
        print(text[:a.max] + (f'\n…(+{len(text) - a.max}자)' if len(text) > a.max else ''))
        sys.exit(rc)

    if a.cmd == 'w':
        if not (a.sql and a.why and a.yes):
            raise SystemExit('w 는 SQL · --why · --yes 필수')
        if not (a.revert or a.no_revert):
            raise SystemExit('--revert "<원복 SQL>" 또는 --no-revert "<이유>" 필수')
        check_write(cfg, a.sql, a.target_ok)
        rows = read_log(run)
        rec = {'id': (max([r.get('id', 0) for r in rows]) + 1) if rows else 1, 'at': U.now(), 'lane': a.lane,
               'why': a.why, 'sql': a.sql, 'revert': a.revert, 'no_revert': a.no_revert}
        rc, out, err = run_sql(cfg, 'write', a.sql)
        rec['rc'] = rc
        U.append_jsonl(log_path(run), rec)
        print(f'write #{rec["id"]} rc={rc}', U.mask((out or err).strip(), cfg)[:800])
        sys.exit(rc)

    if a.cmd == 'log':
        for r in read_log(run):
            tag = 'reverted' if r.get('reverted') else ('no-revert' if r.get('no_revert') else 'open')
            print(f"#{r.get('id')} {r.get('at')} {r.get('lane', ''):8} {tag:9} {r.get('why', '')[:60]} :: {U.mask(r.get('sql', ''), cfg)[:120]}")
        return

    if a.cmd == 'revert':
        rows = read_log(run)
        done = {r['revert_of'] for r in rows if r.get('revert_of')}
        todo = [r for r in rows if r.get('revert') and not r.get('revert_of') and r.get('id') not in done and r.get('rc', 0) == 0]
        if a.id:
            todo = [r for r in todo if r['id'] == a.id]
        elif not a.all:
            raise SystemExit('--id N 이나 --all')
        for r in reversed(todo):
            print(f"revert #{r['id']}: {U.mask(r['revert'], cfg)[:160]}")
            if a.dry:
                continue
            rc, out, err = run_sql(cfg, 'write', r['revert'])
            U.append_jsonl(log_path(run), {'at': U.now(), 'revert_of': r['id'], 'sql': r['revert'], 'rc': rc})
            if rc != 0:
                raise SystemExit(f'원복 실패 #{r["id"]}: {U.mask(err, cfg)[:400]}')
        print(('dry — ' if a.dry else '') + f'{len(todo)}건')


if __name__ == '__main__':
    main()
