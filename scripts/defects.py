#!/usr/bin/env python
"""확정 결함 목록(RUN/defects.json) 관리 — 메인이 감사를 끝낸 결함만 올린다.

  python defects.py list [--status open,qa] [--sev Critical,Major]
  python defects.py show <ID>
  python defects.py add --id UAT3-01 --sev Critical --area "주문서 작성" --title "…" --tcs D-12,D-01 \
        --summary "…" --repro "…" --evidence "…" [--cause "…"] [--tracker ABC-577] [--status open]
  python defects.py add --from new.json            (객체 하나 또는 배열 — 같은 id 면 갱신)
  python defects.py set <ID> [--status qa] [--tracker ABC-577] [--sev Major] [--reopened-as UAT4-02] [--note "…"]
  python defects.py next-id --round 3              다음 ID(UAT<회차>-<두 자리>)

상태: open(미수정) · qa(수정 반영, 재측정 전) · fixed(재측정 통과) · reopened(재발 — 새 결함으로 이어짐) ·
      accepted(수용된 보류 — 사람 결정) · dup(중복). GO 판정은 open·qa·reopened 를 미해결로 센다.
트래커 키는 `tracker`(호환을 위해 `jira` 도 읽는다)에 둔다. 본문·재현 절차에 비밀 값을 쓰면 거부한다.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uatlib as U  # noqa: E402

STATUSES = ('open', 'qa', 'fixed', 'reopened', 'accepted', 'dup')
FIELDS = ('id', 'sev', 'area', 'status', 'tracker', 'title', 'tcs', 'summary', 'cause', 'repro', 'evidence', 'round')


def check(d, cfg):
    if d.get('sev') not in U.SEV_ORDER:
        raise SystemExit(f"{d.get('id')}: sev 는 Critical|Major|Minor")
    if d.get('status', 'open') not in STATUSES:
        raise SystemExit(f"{d.get('id')}: status 는 {'|'.join(STATUSES)}")
    for k, v in d.items():  # 본문 필드 전부 — 선택 필드(fix_hint·expected 등)도 트래커로 옮겨진다
        if not isinstance(v, (str, list)):
            continue
        hit = U.find_secret_like(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False), cfg)  # history 메모 포함
        if hit:
            raise SystemExit(f"{d.get('id')}: {k} 에 비밀처럼 보이는 값({hit}) — 별칭으로 바꿀 것")


def upsert(defects, d):
    for i, x in enumerate(defects):
        if x.get('id') == d['id']:
            merged = dict(x)
            merged.update({k: v for k, v in d.items() if v not in (None, '')})
            defects[i] = merged
            return 'updated'
    defects.append(d)
    return 'added'


def main():
    U.utf8_stdout()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('cmd', choices=['list', 'show', 'add', 'set', 'next-id'])
    p.add_argument('target', nargs='?')
    p.add_argument('--run')
    p.add_argument('--config')
    p.add_argument('--from', dest='src')
    p.add_argument('--round', type=int)
    for f in ('id', 'sev', 'area', 'title', 'tcs', 'summary', 'cause', 'repro', 'evidence', 'tracker', 'status', 'note'):
        p.add_argument('--' + f)
    p.add_argument('--reopened-as')
    a = p.parse_args()
    run = U.find_run(a.run)
    cfg = U.load_config(run, a.config)
    defects = U.load_defects(run)
    info = U.load_run(run)

    if a.cmd == 'list':
        st = set((a.status or '').split(',')) - {''}
        sv = set((a.sev or '').split(',')) - {''}
        for d in sorted(defects, key=lambda d: (U.SEV_ORDER.get(d.get('sev'), 3), d.get('id', ''))):
            if st and d.get('status') not in st:
                continue
            if sv and d.get('sev') not in sv:
                continue
            print(f"{d['id']:9} {d.get('sev', ''):8} {d.get('status', ''):9} {str(d.get('tracker') or d.get('jira') or '-'):11} "
                  f"{','.join(d.get('tcs') or []):18} {d.get('title', '')[:110]}")
        return
    if a.cmd == 'show':
        for d in defects:
            if d.get('id') == a.target:
                print(json.dumps(d, ensure_ascii=False, indent=1))
                return
        raise SystemExit(f'{a.target} 없음')
    if a.cmd == 'next-id':
        rnd = a.round or info.get('round') or 1
        nums = [int(m.group(1)) for d in defects for m in [re.match(rf'UAT{rnd}-(\d+)$', d.get('id', ''))] if m]
        print(f'UAT{rnd}-{(max(nums) + 1) if nums else 1:02d}')
        return
    if a.cmd == 'add':
        items = []
        if a.src:
            obj = json.load(open(a.src, encoding='utf-8'))
            items = obj if isinstance(obj, list) else [obj]
        else:
            if not (a.id and a.sev and a.title):
                raise SystemExit('add 는 --id --sev --title 필수(또는 --from)')
            items = [{
                'id': a.id, 'sev': a.sev, 'area': a.area, 'status': a.status or 'open', 'tracker': a.tracker,
                'title': a.title, 'tcs': [x.strip() for x in (a.tcs or '').split(',') if x.strip()],
                'summary': a.summary, 'cause': a.cause, 'repro': a.repro, 'evidence': a.evidence,
                'round': info.get('round'),
            }]
        for d in items:
            d.setdefault('status', 'open')
            d.setdefault('round', info.get('round'))
            check(d, cfg)
            print(upsert(defects, d), d['id'])
        U.save_defects(run, defects)
        return
    if a.cmd == 'set':
        for d in defects:
            if d.get('id') == a.target:
                if a.status:
                    if a.status not in STATUSES:
                        raise SystemExit(f"status 는 {'|'.join(STATUSES)}")
                    d['status'] = a.status
                if a.tracker:
                    d['tracker'] = a.tracker
                if a.sev:
                    d['sev'] = a.sev
                if a.reopened_as:
                    d['reopened_as'] = a.reopened_as
                    d['status'] = 'reopened'
                if a.note:
                    d.setdefault('history', []).append({'at': U.now(), 'note': a.note})
                check(d, cfg)
                U.save_defects(run, defects)
                print('set', a.target, d.get('status'), d.get('tracker') or '')
                return
        raise SystemExit(f'{a.target} 없음')


if __name__ == '__main__':
    main()
