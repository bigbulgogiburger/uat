#!/usr/bin/env python
"""레인 계획 — 이번 회차에 잴 TC 를 고르고 레인(측정 단위)으로 나눈 뒤 Workflow 인자를 만든다.

  python plan_lanes.py full                                   전 TC (1차)
  python plan_lanes.py remeasure [--extra D-12,M-04] [--skip X-13] [--no-grade1]
                                                              등급1 ∪ 지난 F·BLOCKED ∪ 미해결 결함 TC ∪ 미측정 ∪ extra
  python plan_lanes.py args [--model opus] [--effort xhigh] [--guide PATH] [--out RUN/lanes/workflow-args.json]
  python plan_lanes.py show                                   지금 매니페스트 요약

분할 규칙(프로필 lanes.*):
- method 가 api_methods(기본 ["api"]) 면 API 레인 — api_chunk 개씩. UI 와 병렬로 돈다.
- isolated {레인: [TC…]}  — 서버 재기동 등 다른 레인의 상태를 지우는 TC. 다른 레인이 끝난 뒤에 돈다.
- route_rules [{lane, match, field?}] — 영역과 상관없이 특정 레인으로 모은다(예: 「탈퇴」가 든 TC → auth 레인).
- ui_groups [[레인, "영역문자들"], …] — 이 순서로 돈다. 어디에도 안 걸린 TC 는 misc 레인(경고).
- after_api [레인…] — 세션·계정을 파괴하는 레인. API 레인이 끝난 뒤에 돈다.
- chunk — UI 레인 한 묶음의 최대 TC 수(기본 16). 넘으면 균등하게 나눈다.
지우는 것: lanes/*.jsonl · manifest.json · why.json · workflow-args.json. notes-*.md · changes*.md · recheck*.md 는 보존한다.
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uatlib as U  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def ids_arg(s):
    return [x.strip() for x in (s or '').split(',') if x.strip()]


def select_remeasure(run, cfg, tcs, extra, skip, grade1=True):
    latest, _, _, _ = U.load_verdicts(run)
    why = collections.OrderedDict()

    def add(tid, reason):
        if tid in tcs:
            why.setdefault(tid, []).append(reason)

    if grade1:
        for tid, t in tcs.items():
            if int(t.get('grade', 9)) == 1:
                add(tid, '등급1')
    for tid, r in latest.items():
        if r.get('v') in ('F', 'BLOCKED'):
            add(tid, f'지난 {r["v"]}')
    for d in U.load_defects(run):
        if d.get('status') in U.OPEN_STATUSES:
            for tid in d.get('tcs') or []:
                add(tid, f'결함 {d.get("id")}({d.get("status") or "open"})')
    for tid in tcs:
        if tid not in latest:
            add(tid, '미측정')
    for tid in extra:
        if tid not in tcs:
            print('WARN extra 에 없는 TC', tid)
        add(tid, 'extra')
    keep_always = {tid for tid, rs in why.items() if any(r.startswith('결함') or r == 'extra' for r in rs)}
    for tid in list(why):
        if tid in skip and tid not in keep_always:
            del why[tid]
    return why


def split(cfg, tcs_sel):
    L = cfg['lanes']
    api_methods = set(L.get('api_methods') or ['api'])
    chunk = int(L.get('chunk') or 16)
    api_chunk = int(L.get('api_chunk') or 24)
    isolated = {name: set(ids) for name, ids in (L.get('isolated') or {}).items()}
    rules = L.get('route_rules') or []
    groups = [(g[0], g[1]) for g in (L.get('ui_groups') or [])]
    after = set(L.get('after_api') or []) | set(isolated)

    api, lanes = [], collections.OrderedDict((name, []) for name, _ in groups)
    iso = collections.OrderedDict((name, []) for name in isolated)
    misc = []
    for t in tcs_sel:
        tid = t['id']
        placed = False
        for name, ids in isolated.items():
            if tid in ids:
                iso[name].append(t)
                placed = True
                break
        if placed:
            continue
        if t.get('method') in api_methods:
            api.append(t)
            continue
        for r in rules:
            text = str(t.get(r.get('field') or 'title') or '')
            if re.search(r['match'], text):
                lanes.setdefault(r['lane'], []).append(t)
                placed = True
                break
        if placed:
            continue
        for name, areas in groups:
            if t.get('area') in (areas if isinstance(areas, list) else list(areas)):
                lanes[name].append(t)
                placed = True
                break
        if not placed:
            misc.append(t)
    if misc:
        lanes['misc'] = misc
        print(f'WARN ui_groups 에 안 걸린 TC {len(misc)}건 → misc 레인:', ' '.join(t['id'] for t in misc[:20]))

    def chunks(items, size):
        if not items:
            return []
        k = max(1, -(-len(items) // size))
        per = -(-len(items) // k)
        return [items[i * per:(i + 1) * per] for i in range(k) if items[i * per:(i + 1) * per]]

    plan = {'api': [], 'ui': []}
    for i, part in enumerate(chunks(api, api_chunk), 1):
        plan['api'].append((f'api-{i}', 'api', part, False))
    for name, items in list(lanes.items()) + list(iso.items()):
        for j, part in enumerate(chunks(items, chunk), 1):
            plan['ui'].append((f'{name}-{j}', name, part, name in after))
    return plan


def write_plan(run, plan, why=None):
    ld = os.path.join(run, 'lanes')
    os.makedirs(ld, exist_ok=True)
    for fn in glob.glob(os.path.join(ld, '*.jsonl')) + [os.path.join(ld, x) for x in ('manifest.json', 'why.json', 'workflow-args.json')]:
        if os.path.exists(fn):
            os.remove(fn)
    manifest = {'api': [], 'ui': []}
    for kind in ('api', 'ui'):
        for name, lane, items, after in plan[kind]:
            path = os.path.join(ld, name + '.jsonl')
            U.write_jsonl(path, items)
            manifest[kind].append({'name': name, 'lane': lane, 'file': path.replace('\\', '/'), 'n': len(items),
                                   'ids': [t['id'] for t in items], 'after_api': after})
    U.write_json(os.path.join(ld, 'manifest.json'), manifest)
    if why is not None:
        U.write_json(os.path.join(ld, 'why.json'), why)
    return manifest


def show(manifest, why=None):
    tot = 0
    for kind in ('api', 'ui'):
        for e in manifest[kind]:
            tot += e['n']
            flag = ' (after_api)' if e.get('after_api') else ''
            print(f"{kind:3s} {e['name']:14s} {e['n']:3d}  {e['ids'][0]}..{e['ids'][-1]}{flag}")
    print('합계', tot, 'TC ·', len(manifest['api']), 'API 레인 ·', len(manifest['ui']), 'UI 레인')
    if why:
        c = collections.Counter(r.split('(')[0] if r.startswith('결함') else r for rs in why.values() for r in rs)
        print('선정 사유', dict(c))


def make_args(run, cfg, a):
    man = json.load(open(os.path.join(run, 'lanes', 'manifest.json'), encoding='utf-8'))
    info = U.load_run(run)
    for kind in ('api', 'ui'):
        for e in man[kind]:
            e['model'] = a.model or cfg['lanes'].get('model') or 'opus'
            e['effort'] = a.effort or cfg['lanes'].get('effort') or 'xhigh'
    prev_rounds = sorted({U.round_of_file(f) for f in glob.glob(os.path.join(run, 'out', '*.jsonl'))} - {None})
    guide = U.expand(a.guide or cfg.get('lane_guide') or os.path.join(os.path.dirname(run), 'lane-guide.md'))
    if not os.path.exists(guide):
        print('WARN 레인 가이드가 없다:', guide, '— assets/templates/lane-guide.md 를 채워 둘 것')
    body = {
        'project': cfg.get('project'),
        'run': run.replace('\\', '/'),
        'config': (cfg.get('_path') or '').replace('\\', '/'),
        'tools': HERE.replace('\\', '/'),
        'guide': guide.replace('\\', '/'),
        'build': info.get('build') or '(run.json 에 build 없음)',
        'round': info.get('round'),
        'prev_rounds': prev_rounds,
        'driver': (cfg.get('drivers') or {}).get('ui', 'android'),
        'ui_parallel': int(cfg['lanes'].get('ui_parallel') or 1),
        'repo': cfg.get('repo'),
        'api': man['api'],
        'ui': man['ui'],
    }
    out = a.out or os.path.join(run, 'lanes', 'workflow-args.json')
    with open(out, 'w', encoding='utf-8', newline='') as f:  # BOM 없이
        json.dump(body, f, ensure_ascii=False)
    print('wrote', out.replace('\\', '/'), '·', len(man['api']), 'api ·', len(man['ui']), 'ui · prev_rounds', prev_rounds)


def main():
    U.utf8_stdout()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('mode', choices=['full', 'remeasure', 'args', 'show'])
    p.add_argument('--run')
    p.add_argument('--config')
    p.add_argument('--extra', default='')
    p.add_argument('--skip', default='')
    p.add_argument('--no-grade1', action='store_true')
    p.add_argument('--model')
    p.add_argument('--effort')
    p.add_argument('--guide')
    p.add_argument('--out')
    a = p.parse_args()
    run = U.find_run(a.run)
    cfg = U.load_config(run, a.config)
    if a.mode == 'args':
        return make_args(run, cfg, a)
    if a.mode == 'show':
        mp = os.path.join(run, 'lanes', 'manifest.json')
        wp = os.path.join(run, 'lanes', 'why.json')
        return show(json.load(open(mp, encoding='utf-8')), json.load(open(wp, encoding='utf-8')) if os.path.exists(wp) else None)
    tcs = U.load_tcs(run)
    if not tcs:
        raise SystemExit('tc.jsonl 이 비었다 — tc_merge.py 먼저')
    if a.mode == 'full':
        sel, why = list(tcs.values()), None
    else:
        skip = set(ids_arg(a.skip)) | set(cfg['lanes'].get('skip') or [])
        why = select_remeasure(run, cfg, tcs, ids_arg(a.extra), skip, grade1=not a.no_grade1)
        sel = [tcs[tid] for tid in tcs if tid in why]
    man = write_plan(run, split(cfg, sel), why)
    show(man, why)


if __name__ == '__main__':
    main()
