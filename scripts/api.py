#!/usr/bin/env python
"""UAT API 러너 — 비밀 값(계정 번호·인증번호·토큰)을 출력하지 않고 API 를 직접 부른다.

  python api.py [--as ALIAS] [-H 'K: V']… [--headers] [--no-auth] METHOD PATH [JSON | @파일]
  python api.py login ALIAS [--fresh]       프로필 api.login 시퀀스로 로그인 → 토큰을 RUN/work/.tok-<ALIAS>.json 에 캐시
  python api.py refresh ALIAS               api.refresh 시퀀스(회전) — 이전 REFRESH 는 REFRESH_PREV 로 남긴다
  python api.py forget ALIAS                캐시 삭제

자리표시자 — 경로·본문·헤더 어디든 쓸 수 있고 실행 때 실제 값으로 바뀐다(값은 출력되지 않는다):
  {{계정별칭.KEY}}  예) {{acct1.PHONE}} {{acct2.ACCESS}} {{acct2.REFRESH_PREV}}
  {{@.KEY}}         --as 로 준 별칭
값의 출처: 비밀 파일(secrets_file — 별칭별 PHONE·CODE·PASSWORD …) + 토큰 캐시(ACCESS·REFRESH·REFRESH_PREV).
--as 를 주면 프로필 api.auth_header 를 붙인다(캐시가 없거나 만료면 먼저 로그인). --no-auth 로 끈다.
출력의 비밀 값은 <별칭.KEY> 로, 프로필 redact_patterns 에 걸리는 값은 <redacted> 로 가린다.
토큰 캐시 파일을 열어 출력하지 말 것.

프로필 예(assets/uat.config.example.json 의 api):
  "base_url": "http://localhost:8080/api",
  "default_headers": {"X-Forwarded-For": "203.0.113.10"},
  "auth_header": {"Authorization": "Bearer {{@.ACCESS}}"},
  "login": [{"method": "POST", "path": "/auth/sms/send", "body": {"phone": "{{@.PHONE}}"}},
            {"method": "POST", "path": "/auth/sms/verify", "body": {"phone": "{{@.PHONE}}", "code": "{{@.CODE}}"},
             "save": {"ACCESS": "data.accessToken", "REFRESH": "data.refreshToken"}}],
  "refresh": [{"method": "POST", "path": "/auth/token/refresh", "body": {"refreshToken": "{{@.REFRESH}}"},
               "save": {"ACCESS": "data.accessToken", "REFRESH": "data.refreshToken"}}],
  "token_ttl_s": 600
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uatlib as U  # noqa: E402

PH = re.compile(r'\{\{\s*([@A-Za-z0-9_-]+)\.([A-Za-z0-9_]+)\s*\}\}')
SHOW_HEADERS = ('Content-Type', 'Location', 'Retry-After', 'Set-Cookie', 'WWW-Authenticate')


class Ctx:
    def __init__(self, run, cfg, alias):
        self.run, self.cfg, self.alias = run, cfg, alias
        self.api = cfg.get('api') or {}
        self.secrets = U.load_secrets(cfg)

    def cache_path(self, alias):
        return os.path.join(self.run, 'work', f'.tok-{alias}.json')

    def cache(self, alias):
        p = self.cache_path(alias)
        return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}

    def save_cache(self, alias, values):
        c = self.cache(alias)
        c.setdefault('values', {}).update(values)
        c['saved_at'] = time.time()
        os.makedirs(os.path.dirname(self.cache_path(alias)), exist_ok=True)
        json.dump(c, open(self.cache_path(alias), 'w', encoding='utf-8'))

    def values(self, alias):
        v = dict(self.secrets.get(alias) or {})
        v.update(self.cache(alias).get('values') or {})
        return v

    def all_values(self):
        aliases = set(self.secrets)
        wd = os.path.join(self.run, 'work')
        if os.path.isdir(wd):
            aliases |= {f[5:-5] for f in os.listdir(wd) if f.startswith('.tok-') and f.endswith('.json')}
        return {alias: self.values(alias) for alias in aliases}

    def fill(self, text, alias=None):
        if not isinstance(text, str) or '{{' not in text:
            return text

        def rep(m):
            a = alias or self.alias if m.group(1) == '@' else m.group(1)
            if not a:
                raise SystemExit('{{@.…}} 를 쓰려면 --as 가 필요하다')
            v = self.values(a).get(m.group(2))
            if v is None:
                raise SystemExit(f'자리표시자 {{{{{m.group(1)}.{m.group(2)}}}}} 의 값이 없다(비밀 파일이나 로그인 캐시 확인)')
            return str(v)
        return PH.sub(rep, text)

    def fill_obj(self, obj, alias=None):
        if isinstance(obj, dict):
            return {k: self.fill_obj(v, alias) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.fill_obj(v, alias) for v in obj]
        return self.fill(obj, alias)

    def mask(self, text):
        return U.mask(text, self.cfg, self.all_values())


def http(ctx, method, path, body=None, headers=None, alias=None):
    base = ctx.api.get('base_url') or ''
    url = path if path.startswith('http') else base.rstrip('/') + '/' + path.lstrip('/')
    url = ctx.fill(url, alias)
    h = {'Accept': 'application/json'}
    for k, v in (ctx.api.get('default_headers') or {}).items():
        h[k] = ctx.fill(v, alias)
    for k, v in (headers or {}).items():
        if v == '':
            h.pop(k, None)
        else:
            h[k] = ctx.fill(v, alias)
    data = None
    if body is not None:
        data = json.dumps(ctx.fill_obj(body, alias)).encode() if not isinstance(body, (bytes, str)) else ctx.fill(body, alias).encode()
        h.setdefault('Content-Type', 'application/json')
    req = urllib.request.Request(url, data=data, method=method.upper(), headers=h)
    try:
        with urllib.request.urlopen(req, timeout=float(ctx.api.get('timeout_s', 30))) as r:
            return r.status, dict(r.headers), r.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read().decode('utf-8', errors='replace')
    except urllib.error.URLError as e:
        raise SystemExit(f'연결 실패: {e.reason} — 서버가 떠 있는지 확인(서버를 임의로 재시작하지 말 것)')


def jget(obj, dotted):
    for part in dotted.split('.'):
        if isinstance(obj, list) and part.isdigit():
            obj = obj[int(part)]
        elif isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def run_steps(ctx, alias, steps, label):
    saved = {}
    for i, st in enumerate(steps, 1):
        status, _, text = http(ctx, st.get('method', 'POST'), st['path'], st.get('body'), st.get('headers'), alias)
        print(f'{label} step {i}: HTTP {status}')
        if status >= 400:
            print(ctx.mask(text)[:600])
            raise SystemExit(f'{label} 실패(step {i})')
        if st.get('save'):
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                raise SystemExit(f'{label} step {i}: JSON 응답이 아니다')
            for key, path in st['save'].items():
                v = jget(obj, path)
                if v is None:
                    raise SystemExit(f'{label} step {i}: 응답에 {path} 가 없다')
                saved[key] = v
            if st.get('report'):
                print('  ', ctx.mask(str({k: jget(obj, p) for k, p in st['report'].items()})))
    return saved


def ensure_login(ctx, alias, fresh=False):
    c = ctx.cache(alias)
    ttl = float(ctx.api.get('token_ttl_s', 600))
    if not fresh and c.get('values', {}).get('ACCESS') and time.time() - c.get('saved_at', 0) < ttl:
        return
    steps = ctx.api.get('login') or []
    if not steps:
        raise SystemExit('프로필 api.login 이 없다 — 로그인 시퀀스를 적거나 토큰 없이 부를 것(--no-auth)')
    ctx.save_cache(alias, run_steps(ctx, alias, steps, f'login {alias}'))
    print(f'logged in as {alias} (토큰 캐시 갱신 — 값은 출력하지 않는다)')


def main():
    U.utf8_stdout()
    argv = sys.argv[1:]
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--run')
    p.add_argument('--config')
    p.add_argument('--as', dest='alias')
    p.add_argument('-H', action='append', default=[])
    p.add_argument('--headers', action='store_true')
    p.add_argument('--no-auth', action='store_true')
    p.add_argument('--fresh', action='store_true')
    p.add_argument('--max', type=int, default=6000, help='본문 출력 최대 글자')
    p.add_argument('rest', nargs='+')
    a = p.parse_args(argv)
    run = U.find_run(a.run)
    cfg = U.load_config(run, a.config)
    ctx = Ctx(run, cfg, a.alias)
    os.makedirs(os.path.join(run, 'work'), exist_ok=True)
    cmd = a.rest[0].lower()
    if cmd in ('login', 'refresh', 'forget'):
        alias = a.rest[1] if len(a.rest) > 1 else a.alias
        if not alias:
            raise SystemExit(f'{cmd} 할 별칭이 필요하다')
        if cmd == 'forget':
            if os.path.exists(ctx.cache_path(alias)):
                os.remove(ctx.cache_path(alias))
            print('forgot', alias)
        elif cmd == 'login':
            ensure_login(ctx, alias, fresh=True)
        else:
            prev = ctx.values(alias).get('REFRESH')
            saved = run_steps(ctx, alias, ctx.api.get('refresh') or [], f'refresh {alias}')
            if prev:
                saved['REFRESH_PREV'] = prev
            ctx.save_cache(alias, saved)
            print(f'refreshed {alias} (이전 refresh 는 {{{{{alias}.REFRESH_PREV}}}})')
        return
    if len(a.rest) < 2:
        raise SystemExit('METHOD PATH [JSON|@파일] 형식')
    method, path = a.rest[0], a.rest[1]
    body = None
    if len(a.rest) > 2:
        raw = a.rest[2]
        if raw.startswith('@'):
            raw = open(raw[1:], encoding='utf-8').read()
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = raw
    headers = {}
    for h in a.H:
        k, _, v = h.partition(':')
        headers[k.strip()] = v.strip()
    if a.alias and not a.no_auth:
        ensure_login(ctx, a.alias, fresh=a.fresh)
        for k, v in (ctx.api.get('auth_header') or {}).items():
            headers.setdefault(k, v)
    status, rh, text = http(ctx, method, path, body, headers, a.alias)
    print(f'HTTP {status}')
    if a.headers:
        for k in SHOW_HEADERS:
            for hk, hv in rh.items():
                if hk.lower() == k.lower():
                    print(f'{hk}: {ctx.mask(hv)}')
    try:
        text = json.dumps(json.loads(text), ensure_ascii=False, indent=1)
    except (json.JSONDecodeError, TypeError):
        pass
    out = ctx.mask(text)
    print(out[:a.max] + (f'\n…(+{len(out) - a.max}자)' if len(out) > a.max else ''))


if __name__ == '__main__':
    main()
