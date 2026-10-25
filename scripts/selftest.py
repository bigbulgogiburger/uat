#!/usr/bin/env python
"""스킬 스크립트 자가 점검 — 임시 폴더에 가상 프로젝트(쇼핑 앱)를 만들고 1차 → 2차 파이프라인을 끝까지 돌린다.

  python selftest.py [--keep]        --keep = 임시 폴더를 지우지 않고 경로를 출력

기기·서버·DB 없이 돈다(api.py 는 로컬 sink.py 를 상대로, db.py 는 거부 경로만 본다). 실패하면 종료 코드 1.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
PY = sys.executable
FAILS = []


def run(args, env, expect=0, want=None, deny=None, label=None):
    r = subprocess.run([PY, *args], capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)
    out = (r.stdout or '') + (r.stderr or '')
    ok = (r.returncode == expect) if expect is not None else True
    if want and want not in out:
        ok = False
    if deny and deny in out:
        ok = False
    tag = label or ' '.join(os.path.basename(a) if i == 0 else a for i, a in enumerate(args))[:90]
    print(('ok   ' if ok else 'FAIL ') + tag)
    if not ok:
        FAILS.append(tag)
        print('     rc', r.returncode, '\n     ' + out.strip().replace('\n', '\n     ')[:1500])
    return out


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    keep = '--keep' in sys.argv
    tmp = tempfile.mkdtemp(prefix='uat-selftest-')
    runs = os.path.join(tmp, 'runs')
    os.makedirs(runs)
    fake_phone = '010' + '5555' + '0101'  # 가짜 번호 — 비밀 검사 경로를 시험하려는 값
    secrets = {'acct1': {'PHONE': fake_phone, 'CODE': '000000'}, 'acct2': {'PHONE': '010' + '5555' + '0202', 'CODE': '000000'}}
    json.dump(secrets, open(os.path.join(tmp, 'secrets.json'), 'w', encoding='utf-8'))
    port = free_port()
    cfg = json.load(open(os.path.join(SKILL, 'assets', 'uat.config.example.json'), encoding='utf-8'))
    cfg.update({'runs_dir': runs, 'secrets_file': os.path.join(tmp, 'secrets.json'), 'repo': tmp,
                'lane_guide': os.path.join(SKILL, 'assets', 'templates', 'lane-guide.md')})
    cfg['api'].update({'base_url': f'http://127.0.0.1:{port}/api/v1', 'login': [
        {'method': 'POST', 'path': '/auth/sms/verify', 'body': {'phone': '{{@.PHONE}}', 'code': '{{@.CODE}}'},
         'save': {'ACCESS': 'data.accessToken', 'REFRESH': 'data.refreshToken'}}]})
    cfg['db'] = {'read': [PY, '-c', 'print("1")', '{sql}'], 'write': [PY, '-c', 'print("ok")', '{sql}'], 'write_guard': 'UAT'}
    cfg_path = os.path.join(tmp, 'uat.config.json')
    json.dump(cfg, open(cfg_path, 'w', encoding='utf-8'), ensure_ascii=False)
    env = dict(os.environ, UAT_CONFIG=cfg_path, PYTHONIOENCODING='utf-8')
    env.pop('UAT_RUN', None)
    S = lambda name: os.path.join(HERE, name)  # noqa: E731

    print('— 1차')
    run([S('init_run.py'), '--round', '1', '--build', 'aaaa111', '--date', '2026-01-10'], env)
    r1 = os.path.join(runs, '2026-01-10-uat1')
    env1 = dict(env, UAT_RUN=r1)
    os.makedirs(os.path.join(r1, 'tc-draft'), exist_ok=True)
    shutil.copy(os.path.join(SKILL, 'assets', 'examples', 'tc.example.jsonl'), os.path.join(r1, 'tc-draft', 'order.jsonl'))
    bad = os.path.join(r1, 'tc-draft', 'bad.jsonl')
    open(bad, 'w', encoding='utf-8').write(json.dumps({'id': 'D-99', 'area': 'D', 'grade': 1, 'title': 't', 'steps': 's',
                                                       'expected': '정상 동작', 'method': 'ui', 'feasibility': 'ok',
                                                       'source': 'x', 'pre': f'번호 {fake_phone}'}, ensure_ascii=False) + '\n')
    run([S('tc_merge.py'), '--check'], env1, expect=1, want='정상 동작', label='tc_merge 가 「정상 동작」·비밀 값을 거부')
    os.remove(bad)
    run([S('tc_merge.py')], env1, label='tc_merge 병합')
    head = os.path.join(SKILL, 'assets', 'templates', 'checklist-head.md')
    run([S('render_checklist.py'), '--head', head, '--out', os.path.join(tmp, 'docs', 'checklist.md')], env1)
    md = open(os.path.join(tmp, 'docs', 'checklist.md'), encoding='utf-8').read()
    if '1) ' not in md or "['" in md:
        FAILS.append('render_checklist 배열 렌더')
        print('FAIL render_checklist 배열 렌더')
    run([S('plan_lanes.py'), 'full'], env1)
    run([S('plan_lanes.py'), 'args'], env1, want='wrote')
    args = json.load(open(os.path.join(r1, 'lanes', 'workflow-args.json'), encoding='utf-8'))
    if not args.get('api') or not args.get('ui'):
        FAILS.append('workflow-args 에 api/ui 레인')
        print('FAIL workflow-args 에 api/ui 레인', args.get('api'), args.get('ui'))

    V = S('verdict.py')
    run([V, '--lane', 'order', '--tc', 'D-01', '--v', 'P'], env1, expect=None, want='evidence', label='P 인데 증거 없음 → 거부')
    run([V, '--lane', 'order', '--tc', 'D-01', '--v', 'F', '--sev', 'Critical', '--actual', '제출 안 됨', '--evidence', 'shots/d01.png',
         '--repro', '1) 주문하기 2) 결제하기'], env1, label='F 기록')
    run([V, '--lane', 'order', '--tc', 'D-07', '--v', 'P', '--evidence', f'계정 {fake_phone} 로 확인'], env1, expect=None,
        deny='recorded', label='증거에 번호 → 거부')
    run([V, '--lane', 'order', '--tc', 'D-07', '--v', 'P', '--evidence', 'shots/d07.png'], env1, label='P 기록')
    run([V, '--lane', 'order', '--tc', 'D-12', '--v', 'BLOCKED', '--actual', '[순서 필요: 빈 계정] 계정#3 필요'], env1, label='BLOCKED 기록')
    run([V, '--lane', 'order', '--side', '--area', 'D', '--sev', 'Major', '--title', '결제 결과에서 뒤로가면 빈 화면',
         '--actual', '빈 화면', '--evidence', 'shots/side1.png', '--repro', '결제 → 뒤로'], env1, label='부수 결함 기록')
    run([V, '--lane', 'order', '--tc', 'ZZ-01', '--v', 'P', '--evidence', 'x'], env1, expect=None, deny='recorded', label='없는 TC → 거부')
    run([V, '--summary', '--lane', 'order'], env1, want='D-01')
    run([S('triage.py'), '--json', os.path.join(r1, 'triage.json')], env1)
    run([S('defects.py'), 'add', '--from', os.path.join(SKILL, 'assets', 'examples', 'defects.example.json')], env1, label='defects add --from')
    run([S('defects.py'), 'list'], env1, want='UAT3-01')
    run([S('render_results.py'), '--stats'], env1, want='NO-GO' if False else None, label='render_results --stats')
    out_md = os.path.join(tmp, 'docs', 'results.md')
    run([S('render_results.py'), '--round', '1', '--date', '2026-01-10', '--build', 'aaaa111', '--out', out_md, '--note', '범위 전수'], env1)
    if 'NO-GO' not in open(out_md, encoding='utf-8').read():
        FAILS.append('결과보고 NO-GO')
        print('FAIL 결과보고 NO-GO')

    print('— api.py · sink.py')
    rules = os.path.join(tmp, 'rules.json')
    json.dump([{'match': '/auth/sms/verify', 'status': 200, 'body': {'data': {'accessToken': 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLXNpZ25hdHVyZQ',
                                                                              'refreshToken': 'r' * 24}}},
               {'match': '/orders', 'status': 200, 'body': {'data': {'owner': fake_phone, 'items': 1}}}], open(rules, 'w'))
    sink = subprocess.Popen([PY, S('sink.py'), '--http', str(port), '--smtp', str(free_port()), '--rules', rules,
                             '--log', os.path.join(r1, 'work', 'sink.log')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env1)
    try:
        for _ in range(50):
            try:
                socket.create_connection(('127.0.0.1', port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        out = run([S('api.py'), '--as', 'acct1', 'GET', '/orders/{{acct2.PHONE}}'], env1, want='HTTP 200', deny=fake_phone,
                  label='api.py 로그인 → 호출 · 응답의 번호 가림')
        if '5555' in out:
            FAILS.append('api.py 출력에 번호 조각')
            print('FAIL api.py 출력에 번호 조각')
        log = open(os.path.join(r1, 'work', 'sink.log'), encoding='utf-8').read()
        if fake_phone in log:
            FAILS.append('sink.log 에 본문 값')
            print('FAIL sink.log 에 본문 값')
    finally:
        sink.terminate()

    print('— db.py 거부 경로')
    D = S('db.py')
    run([D, 'w', 'DROP TABLE orders', '--why', 't', '--no-revert', 'x', '--yes'], env1, expect=None, deny='"id"', want='DDL', label='DDL 거부')
    run([D, 'w', 'UPDATE orders SET s=1', '--why', 't', '--no-revert', 'x', '--yes'], env1, expect=None, want='WHERE', label='WHERE 없는 UPDATE 거부')
    run([D, 'w', "UPDATE orders SET s=1 WHERE name='real'", '--why', 't', '--no-revert', 'x', '--yes'], env1, expect=None,
        want='UAT', label='write_guard 없는 쓰기 거부')
    run([D, 'w', "UPDATE orders SET s=1 WHERE name LIKE 'UAT%'", '--why', 'D-12 준비', '--revert',
         "UPDATE orders SET s=0 WHERE name LIKE 'UAT%'", '--yes'], env1, label='guard 있는 쓰기 + 원복 기록')
    run([D, 'revert', '--all', '--dry'], env1, want='UPDATE orders SET s=0', label='revert --dry')

    print('— 2차')
    run([S('init_run.py'), '--round', '2', '--build', 'bbbb222', '--date', '2026-01-12', '--prev', r1], env)
    r2 = os.path.join(runs, '2026-01-12-uat2')
    env2 = dict(env, UAT_RUN=r2)
    if not os.path.exists(os.path.join(r2, 'out', 'r1-order.jsonl')):
        FAILS.append('init_run --prev 가 r1- 판정 보존')
        print('FAIL init_run --prev 가 r1- 판정 보존')
    out = run([S('plan_lanes.py'), 'remeasure'], env2, label='plan_lanes remeasure')
    why = json.load(open(os.path.join(r2, 'lanes', 'why.json'), encoding='utf-8'))
    for tid in ('D-01', 'D-12', 'X-04'):
        if tid not in why:
            FAILS.append(f'remeasure 가 {tid} 를 고름')
            print(f'FAIL remeasure 가 {tid} 를 고름', sorted(why))
    run([V, '--lane', 'order', '--tc', 'D-01', '--v', 'P', '--evidence', 'shots/d01-r2.png', '--fix', '해소'], env2, label='2차 P + 해소')
    run([V, '--lane', 'api', '--tc', 'X-04', '--v', 'F', '--sev', 'Critical', '--actual', '타 회원 주문이 200 으로 열림',
         '--evidence', 'HTTP 200', '--repro', 'acct2 토큰으로 GET'], env2, label='결함 목록에 없는 Critical F')
    out = run([S('render_results.py'), '--stats'], env2, want='"unaudited_f": ["X-04"]', label='감사 전 Critical F 는 GO 를 막는다')
    if '"go": true' in out:
        FAILS.append('감사 전 F 인데 GO')
        print('FAIL 감사 전 F 인데 GO')
    run([S('triage.py')], env2, label='2차 triage')
    run([S('memguard.py')], env, want='free', label='memguard')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAIL:', *FAILS, sep='\n  ')
    else:
        print('ALL OK')
    if keep:
        print('kept', tmp)
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
