"""UAT 스크립트 공통 — 실행 폴더·프로필 찾기, jsonl 입출력, 판정 병합, 비밀 마스킹.

실행 폴더(RUN) 결정 순서: --run > 환경변수 UAT_RUN > 현재 폴더에서 위로 올라가며 run.json 이 있는 폴더.
프로필(config) 결정 순서: --config > 환경변수 UAT_CONFIG > run.json 의 "config".
"""
import collections
import datetime
import glob
import json
import os
import re
import sys

ROUND_PREFIX = re.compile(r'^r(\d+)-')

# 기본은 좁게 둔다 — 넓은 패턴(국제 전화번호 등)은 접수번호·시각을 잘못 잡아 판정 기록을 막는다.
# 프로젝트에 맞는 패턴은 프로필의 redact_patterns 로 더한다(이 목록을 통째로 바꾼다).
DEFAULT_REDACT = [
    r'(?<!\d)01[016789][-. ]?\d{3,4}[-. ]?\d{4}(?!\d)',              # 한국 휴대폰 번호 꼴
    r'eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}',  # JWT
    r'(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{16,}',                      # Authorization 헤더 값
]

CONFIG_DEFAULTS = {
    'project': 'project',
    'areas': {},
    'methods': ['ui', 'api', 'ui+api', 'ui+db', 'api+db', 'manual'],
    'data_prefix': 'UAT',
    'redact_patterns': DEFAULT_REDACT,
    'lanes': {
        'ui_groups': [],
        'ui_parallel': 1,
        'after_api': [],
        'isolated': {},
        'route_rules': [],
        'chunk': 16,
        'api_chunk': 24,
        'model': 'opus',
        'effort': 'xhigh',
    },
    'carry_work': ['requests.jsonl', 'db-writes.log', 'state-snapshots.json'],
}


def utf8_stdout():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


def now():
    return datetime.datetime.now().isoformat(timespec='seconds')


def expand(p):
    return os.path.abspath(os.path.expandvars(os.path.expanduser(p))) if p else p


def find_run(cli=None, required=True):
    if cli:
        return expand(cli)
    env = os.environ.get('UAT_RUN')
    if env:
        return expand(env)
    d = os.getcwd()
    while True:
        if os.path.exists(os.path.join(d, 'run.json')):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    if required:
        raise SystemExit('실행 폴더를 못 찾았다 — --run 이나 UAT_RUN 을 주거나 run.json 이 있는 폴더에서 실행할 것')
    return None


def load_run(run):
    p = os.path.join(run, 'run.json')
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}


def _merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def config_path(run=None, cli=None):
    if cli:
        return expand(cli)
    if os.environ.get('UAT_CONFIG'):
        return expand(os.environ['UAT_CONFIG'])
    if run:
        c = load_run(run).get('config')
        if c:
            return expand(c)
    return None


def load_config(run=None, cli=None, required=False):
    p = config_path(run, cli)
    if not p or not os.path.exists(p):
        if required:
            raise SystemExit('프로필(uat.config.json)을 못 찾았다 — --config 나 UAT_CONFIG 를 줄 것')
        return _merge(CONFIG_DEFAULTS, {})
    cfg = _merge(CONFIG_DEFAULTS, json.load(open(p, encoding='utf-8')))
    cfg['_path'] = p
    return cfg


def area_order(cfg):
    return list(cfg.get('areas') or {})


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    for ln, line in enumerate(open(path, encoding='utf-8'), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise SystemExit(f'{path}:{ln} JSON 오류 — {e}')
    return rows


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def append_jsonl(path, row):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')


def write_json(path, obj):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write('\n')


def load_tcs(run):
    return collections.OrderedDict((t['id'], t) for t in read_jsonl(os.path.join(run, 'tc.jsonl')))


def round_of_file(name):
    """out/ 파일 이름 → 회차 번호. r<N>- 접두가 없으면 None(= 이번 회차)."""
    m = ROUND_PREFIX.match(os.path.basename(name))
    return int(m.group(1)) if m else None


def load_verdicts(run):
    """out/*.jsonl 을 읽어 (latest, current, sides_all, sides_current) 를 돌려준다.

    - latest: TC → 회차를 가로질러 가장 나중 기록(at 기준). 재확인·재측정이 덮는다.
    - current: TC → 이번 회차(접두 없는 파일) 기록 중 가장 나중 것.
    - sides_*: 철회(withdrawn)되지 않은 부수 결함 기록.
    """
    latest, current, sides_all, sides_cur = {}, {}, [], []
    for fn in sorted(glob.glob(os.path.join(run, 'out', '*.jsonl'))):
        is_cur = round_of_file(fn) is None
        for r in read_jsonl(fn):
            if r.get('side'):
                if not r.get('withdrawn'):
                    sides_all.append(r)
                    if is_cur:
                        sides_cur.append(r)
                continue
            tc = r.get('tc')
            if not tc:
                continue
            at = r.get('at', '')
            if tc not in latest or at >= latest[tc].get('at', ''):
                latest[tc] = r
            if is_cur and (tc not in current or at >= current[tc].get('at', '')):
                current[tc] = r
    return latest, current, sides_all, sides_cur


def load_defects(run):
    p = os.path.join(run, 'defects.json')
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else []


def save_defects(run, defects):
    write_json(os.path.join(run, 'defects.json'), defects)


SEV_ORDER = {'Critical': 0, 'Major': 1, 'Minor': 2}
OPEN_STATUSES = ('open', 'qa', 'reopened', None)


def load_secrets(cfg):
    """secrets_file → {alias: {KEY: value}}. 파일이 없으면 빈 dict. 값은 절대 출력하지 않는다."""
    p = expand(cfg.get('secrets_file') or '')
    if not p or not os.path.exists(p):
        return {}
    d = json.load(open(p, encoding='utf-8'))
    return d.get('aliases', d)


def secret_values(cfg, extra=None):
    """마스킹 대상 (값, 표기) 목록 — 긴 값부터."""
    pairs = []
    for alias, kv in load_secrets(cfg).items():
        for k, v in (kv or {}).items():
            if v is None:
                continue
            s = str(v)
            if len(s) >= 4:
                pairs.append((s, f'<{alias}.{k}>'))
                digits = ''.join(c for c in s if c.isdigit())
                if len(digits) >= 8 and digits != s:
                    pairs.append((digits, f'<{alias}.{k}>'))
    for alias, kv in (extra or {}).items():
        for k, v in (kv or {}).items():
            if v and len(str(v)) >= 4:
                pairs.append((str(v), f'<{alias}.{k}>'))
    return sorted(set(pairs), key=lambda p: -len(p[0]))


def compile_redact(cfg):
    return [re.compile(p) for p in (cfg.get('redact_patterns') or DEFAULT_REDACT)]


def mask(text, cfg, extra=None):
    if not text:
        return text
    for value, label in secret_values(cfg, extra):
        text = text.replace(value, label)
    for pat in compile_redact(cfg):
        text = pat.sub(lambda m: (m.group(1) if m.groups() and m.group(1) else '') + '<redacted>', text)
    return text


def find_secret_like(text, cfg):
    """기록 전에 비밀처럼 보이는 문자열이 있는지 — 있으면 그 패턴 이름을 돌려준다."""
    if not text:
        return None
    for value, label in secret_values(cfg):
        if value in text:
            return label
    for pat in compile_redact(cfg):
        if pat.search(text):
            return pat.pattern[:40]
    return None


def esc_md(s):
    return str(s if s is not None else '').replace('|', '\\|').replace('\n', ' ')
