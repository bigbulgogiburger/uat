#!/usr/bin/env python
"""Android 에뮬레이터·기기 화면 조작(adb + uiautomator). 비밀 값은 다루지 않는다(비밀 입력은 secret_type.py).

  python ui.py dump [--all]                     화면 요소 목록(문구·좌표·플래그 C=클릭 S=스크롤 F=포커스 ✓=선택 x=비활성)
  python ui.py find <문구> [--exact]            문구가 들어간 요소
  python ui.py tap <문구> [--exact] [--nth N]   요소 중심을 탭(짧은 라벨 = 정확히 그 버튼을 우선)
  python ui.py tapxy <x> <y>
  python ui.py type <텍스트>                    포커스된 입력칸에 입력(ASCII 는 키 입력, 그 외는 클립보드 붙여넣기)
  python ui.py clear [N]                        포커스된 입력칸 비우기
  python ui.py key back|enter|home|tab|del|esc|<KEYCODE_…>
  python ui.py swipe up|down|left|right [--from y]       up = 손가락을 위로(아래 내용 보기)
  python ui.py shot <이름>                      캡처 → RUN/shots/<이름>.png + <이름>.s.png(축소본 — 이걸 Read 로 연다)
  python ui.py wait <문구> [--timeout 15]
  python ui.py app start|stop|restart|clear     clear = 앱 데이터 삭제(첫 실행 상태)
  python ui.py deeplink <URI>                   VIEW 인텐트로 연다
  python ui.py activity                         지금 앞에 있는 액티비티
  python ui.py log [--lines 80] [--tags flutter:I,AndroidRuntime:E,chromium:I]
  python ui.py net off|on                       비행기 모드로 네트워크 끊기/잇기 — 끝나면 반드시 on

프로필 android: {"adb": "<adb 경로>", "package": "com.example.app",
                 "clip_dex": "/data/local/tmp/uat-clip.dex", "serial": "emulator-5554"}
환경변수 ADB · UAT_PKG · ANDROID_SERIAL 이 있으면 그것이 우선한다.
판정 메모: dump 에 요소가 있다는 것과 사람 눈에 보인다는 것은 다르다(흰 배경에 흰 글씨). 시각 판정은 shot 을 열어서 한다.
"""
import base64
import os
import re
import subprocess
import sys
import time

try:  # uiautomator 덤프는 로컬 기기 출력이지만, 있으면 안전한 파서를 쓴다
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import uatlib as U  # noqa: E402

RUN = U.find_run(None, required=False) or os.getcwd()
CFG = U.load_config(RUN if os.path.exists(os.path.join(RUN, 'run.json')) else None)
A = CFG.get('android') or {}
ADB = os.environ.get('ADB') or A.get('adb') or 'adb'
PKG = os.environ.get('UAT_PKG') or A.get('package') or ''
SERIAL = os.environ.get('ANDROID_SERIAL') or A.get('serial')
CLIP_DEX = A.get('clip_dex') or '/data/local/tmp/uat-clip.dex'
SHOTS = os.path.join(RUN, 'shots')
KEYS = {'back': 'KEYCODE_BACK', 'enter': 'KEYCODE_ENTER', 'home': 'KEYCODE_HOME', 'tab': 'KEYCODE_TAB',
        'del': 'KEYCODE_DEL', 'esc': 'KEYCODE_ESCAPE'}


def adb(*args, check=True, text=True, timeout=60):
    cmd = [ADB] + (['-s', SERIAL] if SERIAL else []) + list(args)
    r = subprocess.run(cmd, capture_output=True, text=text, timeout=timeout,
                       encoding='utf-8' if text else None, errors='replace' if text else None)
    if check and r.returncode != 0:
        raise SystemExit(f'adb {" ".join(args)} failed: {r.stderr or r.stdout}')
    return r.stdout


def nodes():
    out = ''
    for _ in range(3):
        out = adb('exec-out', 'uiautomator', 'dump', '/dev/tty', check=False)
        m = re.search(r'(<\?xml.*</hierarchy>)', out, re.S)
        if m:
            break
        time.sleep(0.7)
    else:
        raise SystemExit('uiautomator dump 실패(애니메이션 중이거나 보안 화면일 수 있다): ' + out[-300:])
    res = []
    for n in ET.fromstring(m.group(1)).iter('node'):
        b = re.findall(r'\d+', n.get('bounds', ''))
        if len(b) != 4:
            continue
        x1, y1, x2, y2 = map(int, b)
        res.append({
            'text': (n.get('text') or '').strip(), 'desc': (n.get('content-desc') or '').strip(),
            'hint': (n.get('hint') or '').strip(), 'cls': n.get('class', '').split('.')[-1],
            'x': (x1 + x2) // 2, 'y': (y1 + y2) // 2, 'w': x2 - x1, 'h': y2 - y1, 'bounds': (x1, y1, x2, y2),
            'click': n.get('clickable') == 'true', 'scroll': n.get('scrollable') == 'true',
            'focus': n.get('focused') == 'true', 'checked': n.get('checked') == 'true' or n.get('selected') == 'true',
            'enabled': n.get('enabled') == 'true', 'pkg': n.get('package', ''),
        })
    return res


def label_of(n):
    return (n['text'] or n['desc'] or n['hint']).replace('\n', ' / ')


def match(q, exact=False):
    q = q.strip()
    out = []
    for n in nodes():
        for s in (n['text'], n['desc'], n['hint']):
            s2 = s.replace('\n', ' ')
            if (exact and s2 == q) or (not exact and q and q in s2):
                out.append(n)
                break
    return out


def tap_xy(x, y):
    adb('shell', 'input', 'tap', str(x), str(y))


def focused_field():
    for n in nodes():
        if n['focus'] and n['cls'] in ('EditText', 'AutoCompleteTextView'):
            return n
    return None


def set_clipboard(s):
    b64 = base64.b64encode(s.encode('utf-8')).decode()
    out = adb('shell', f'CLASSPATH={CLIP_DEX} app_process /system/bin ClipSet {b64}', check=False)
    if 'ok' not in out:
        raise SystemExit('클립보드 설정 실패 — references/drivers.md §1.4 의 ClipSet dex 를 기기에 올렸는지 확인: ' + out[-200:])


def paste_into_focused(s):
    f = focused_field()
    if not f:
        raise SystemExit('포커스된 입력칸이 없다 — 먼저 칸을 탭할 것')
    set_clipboard(s)
    x1, y1, x2, y2 = f['bounds']
    px, py = max(x1 + 20, x2 - 40), (y1 + y2) // 2   # 빈 쪽(오른쪽 끝)을 길게 눌러야 단어 선택 대신 붙여넣기 메뉴가 뜬다
    for _ in range(3):
        adb('shell', 'input', 'swipe', str(px), str(py), str(px), str(py), '900')
        time.sleep(1.0)
        menu = [n for n in nodes() if (n['text'] or n['desc']) in ('Paste', '붙여넣기')]
        if menu:
            tap_xy(menu[0]['x'], menu[0]['y'])
            time.sleep(0.6)
            return
    raise SystemExit('붙여넣기 메뉴가 뜨지 않았다 — 화면 키보드(Gboard)가 메뉴를 가리면 references/drivers.md §1.3')


def type_text(s):
    if re.fullmatch(r'[A-Za-z0-9 @._+-]+', s):
        adb('shell', 'input', 'text', s.replace(' ', '%s'))
        return f'typed {len(s)} chars'
    paste_into_focused(s)
    return f'pasted {len(s)} chars'


def main(argv):
    U.utf8_stdout()
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return
    cmd, rest = argv[0], argv[1:]
    if cmd == 'dump':
        show_all = '--all' in rest
        for i, n in enumerate(nodes()):
            lab = label_of(n)
            if not show_all and not lab and not (n['click'] or n['scroll'] or n['focus']):
                continue
            flags = ''.join(f for f, on in (('C', n['click']), ('S', n['scroll']), ('F', n['focus']),
                                            ('✓', n['checked']), ('x', not n['enabled'])) if on)
            print(f"{i:3d} {n['cls'][:12]:12s} [{flags:3s}] ({n['x']},{n['y']}) {n['w']}x{n['h']} {lab[:110]}")
    elif cmd == 'find':
        q = [x for x in rest if not x.startswith('--')][0]
        for n in match(q, '--exact' in rest):
            print(f"({n['x']},{n['y']}) {n['w']}x{n['h']} click={n['click']} enabled={n['enabled']} :: {label_of(n)[:140]}")
    elif cmd == 'tap':
        nth = int(rest[rest.index('--nth') + 1]) if '--nth' in rest else 0
        q = [x for i, x in enumerate(rest) if not x.startswith('--') and (i == 0 or rest[i - 1] != '--nth')][0]
        ms = match(q, '--exact' in rest)
        if not ms:
            raise SystemExit(f'NOT FOUND: {q} — dump 로 실제 문구를 확인하고, 화면 밖이면 swipe 후 다시')
        ms.sort(key=lambda n: (len(label_of(n)), -n['click']))
        n = ms[min(nth, len(ms) - 1)]
        tap_xy(n['x'], n['y'])
        print(f"tapped ({n['x']},{n['y']}) :: {label_of(n)[:100]}")
    elif cmd == 'tapxy':
        tap_xy(rest[0], rest[1])
        print('tapped', rest[0], rest[1])
    elif cmd == 'type':
        print(type_text(' '.join(rest)))
    elif cmd == 'clear':
        f = focused_field()
        k = int(rest[0]) if rest else (len(f['text']) + 5 if f else 60)
        adb('shell', 'input', 'keyevent', 'KEYCODE_MOVE_END')
        adb('shell', 'input', 'keyevent', *(['KEYCODE_DEL'] * k))
        print('cleared', k)
    elif cmd == 'key':
        adb('shell', 'input', 'keyevent', KEYS.get(rest[0], rest[0]))
        print('key', rest[0])
    elif cmd == 'swipe':
        d = rest[0]
        y0 = int(rest[rest.index('--from') + 1]) if '--from' in rest else None
        size = re.findall(r'(\d+)x(\d+)', adb('shell', 'wm', 'size', check=False))
        W, H = (int(size[-1][0]), int(size[-1][1])) if size else (1080, 1920)
        y0 = y0 or int(H * 0.66)
        args = {'up': (W // 2, y0, W // 2, max(y0 - int(H * 0.43), int(H * 0.12))),
                'down': (W // 2, max(y0 - int(H * 0.43), int(H * 0.12)), W // 2, y0),
                'left': (int(W * 0.87), H // 2, int(W * 0.13), H // 2),
                'right': (int(W * 0.13), H // 2, int(W * 0.87), H // 2)}[d]
        adb('shell', 'input', 'swipe', *map(str, args), '350')
        print('swiped', d)
    elif cmd == 'shot':
        os.makedirs(SHOTS, exist_ok=True)
        png = subprocess.run([ADB] + (['-s', SERIAL] if SERIAL else []) + ['exec-out', 'screencap', '-p'],
                             capture_output=True, timeout=60).stdout
        full = os.path.join(SHOTS, rest[0] + '.png')
        open(full, 'wb').write(png)
        small = os.path.join(SHOTS, rest[0] + '.s.png')
        try:
            from PIL import Image
            im = Image.open(full)
            im.resize((im.width * 3 // 8, im.height * 3 // 8)).convert('RGB').save(small, optimize=True)
            print(small.replace('\\', '/'))
        except ImportError:
            print(full.replace('\\', '/'), '(Pillow 가 없어 축소본을 못 만들었다 — 원본을 연다)')
    elif cmd == 'wait':
        t = float(rest[rest.index('--timeout') + 1]) if '--timeout' in rest else 15
        end = time.time() + t
        while time.time() < end:
            if match(rest[0]):
                print('FOUND', rest[0])
                return
            time.sleep(1)
        raise SystemExit(f'TIMEOUT waiting for: {rest[0]}')
    elif cmd == 'app':
        if not PKG:
            raise SystemExit('프로필 android.package(또는 UAT_PKG)가 없다')
        act = rest[0]
        if act in ('stop', 'restart'):
            adb('shell', 'am', 'force-stop', PKG)
        if act == 'clear':
            adb('shell', 'pm', 'clear', PKG)
        if act in ('start', 'restart', 'clear'):
            adb('shell', 'monkey', '-p', PKG, '-c', 'android.intent.category.LAUNCHER', '1', check=False)
        print('app', act)
    elif cmd == 'deeplink':
        args = ['shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', rest[0]]
        if PKG:
            args += ['-p', PKG]
        print(adb(*args, check=False).strip()[-300:])
    elif cmd == 'activity':
        out = adb('shell', 'dumpsys', 'activity', 'activities', check=False)
        m = re.search(r'(mResumedActivity|topResumedActivity)[^\n]*', out)
        print(m.group(0).strip() if m else out[-300:])
    elif cmd == 'log':
        n = rest[rest.index('--lines') + 1] if '--lines' in rest else '80'
        tags = (rest[rest.index('--tags') + 1] if '--tags' in rest else 'flutter:I,AndroidRuntime:E').split(',')
        print(U.mask(adb('logcat', '-d', '-t', n, '-v', 'time', *tags, '*:S', check=False), CFG)[-8000:])
    elif cmd == 'net':
        on = rest[0] == 'on'
        adb('shell', 'cmd', 'connectivity', 'airplane-mode', 'disable' if on else 'enable')
        time.sleep(2.5 if on else 1.0)
        state = adb('shell', 'settings', 'get', 'global', 'airplane_mode_on', check=False).strip()
        print('network', 'on' if state == '0' else 'off')
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == '__main__':
    main(sys.argv[1:])
