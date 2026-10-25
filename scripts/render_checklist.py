#!/usr/bin/env python
"""tc.jsonl → UAT 체크리스트 문서(md).

  python render_checklist.py --head RUN/checklist-head.md --out <repo>/docs/UAT_체크리스트.md [--run RUN]

head(목적·합격 기준·환경·판정·심각도·등급·저니 — assets/templates/checklist-head.md)를 앞에 붙이고,
영역별 요약표 + TC 상세 블록을 쓴다. 영역 이름·순서는 프로필 areas 를 따른다.
"""
import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uatlib as U  # noqa: E402

FEAS = {'ok': '가능', 'data': '데이터 준비', 'blocked': '환경상 불가'}
FIELDS = (('전제', 'pre'), ('절차', 'steps'), ('기대 결과', 'expected'), ('데이터 준비', 'data_setup'),
          ('측정 제약', 'feasibility_note'), ('근거', 'source'), ('비고', 'notes'))


def fmt(v, key):
    """steps·expected 는 문자열("1) … 2) …")이나 배열 둘 다 받는다."""
    if isinstance(v, list):
        if key == 'steps':
            return ' '.join(f'{i}) {s}' for i, s in enumerate(v, 1))
        return ' · '.join(str(x) for x in v)
    return str(v or '').strip()


def main():
    U.utf8_stdout()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--run')
    p.add_argument('--config')
    p.add_argument('--head', required=True)
    p.add_argument('--out', required=True)
    a = p.parse_args()
    run = U.find_run(a.run)
    cfg = U.load_config(run, a.config)
    names = cfg.get('areas') or {}
    tcs = list(U.load_tcs(run).values())
    by = collections.defaultdict(list)
    for t in tcs:
        by[t['area']].append(t)
    order = list(names) + sorted(k for k in by if k not in names)

    out = [open(a.head, encoding='utf-8').read().rstrip(), '']
    out += ['## 영역별 TC 수', '', '| 영역 | 이름 | TC | 등급1 | 등급2 | 등급3 |', '|---|---|---:|---:|---:|---:|']
    tot = [0, 0, 0, 0]
    for k in order:
        ts = by.get(k, [])
        if not ts:
            continue
        g = [sum(1 for t in ts if int(t['grade']) == i) for i in (1, 2, 3)]
        out.append(f'| {k} | {names.get(k, "")} | {len(ts)} | {g[0]} | {g[1]} | {g[2]} |')
        tot = [tot[0] + len(ts), tot[1] + g[0], tot[2] + g[1], tot[3] + g[2]]
    out += [f'| | **합계** | **{tot[0]}** | **{tot[1]}** | **{tot[2]}** | **{tot[3]}** |', '']
    for k in order:
        ts = by.get(k, [])
        if not ts:
            continue
        out += [f'## {k}. {names.get(k, "")}', '', '| ID | 등급 | 항목 | 화면 | 방법 | 측정 |', '|---|:-:|---|---|---|---|']
        for t in ts:
            out.append(f"| {t['id']} | {t['grade']} | {U.esc_md(t['title'])} | {U.esc_md(', '.join(t.get('screens') or []))} | "
                       f"{U.esc_md(t.get('method'))} | {FEAS.get(t.get('feasibility'), t.get('feasibility'))} |")
        out.append('')
        for t in ts:
            out.append(f"#### {t['id']} · 등급{t['grade']} · {t['title']}")
            if t.get('impl') and t['impl'] != '구현':
                out.append(f"- **구현 상태: {t['impl']}**")
            if t.get('route'):
                out.append(f"- 경로: `{t['route']}`")
            for label, key in FIELDS:
                v = fmt(t.get(key), key)
                if v:
                    out.append(f'- {label}: {v}')
            out.append('')
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, 'w', encoding='utf-8', newline='\n').write('\n'.join(out).rstrip() + '\n')
    print('wrote', a.out, len(tcs), 'TCs')


if __name__ == '__main__':
    main()
