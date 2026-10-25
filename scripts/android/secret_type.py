#!/usr/bin/env python
"""비밀 값(테스트 계정 번호·인증번호·비밀번호)을 포커스된 입력칸에 입력한다 — 값은 출력하지 않는다.

  python secret_type.py <별칭> <KEY> [--digits]      예) secret_type.py acct1 PHONE --digits · secret_type.py acct1 CODE
  python secret_type.py <별칭> <KEY> --mask          화면 대조용 마스킹 표기(앞 3 · 뒤 4)만 출력

값은 프로필 secrets_file 의 {"aliases": {"acct1": {"PHONE": "…", "CODE": "…"}}} 에서 읽는다.
--digits 면 숫자만 남겨 입력한다(하이픈을 화면이 넣어 주는 입력칸). ASCII 가 아닌 값은 클립보드 붙여넣기로 넣는다.
에이전트는 비밀 파일을 직접 열지 않는다 — 이 도구만 연다.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import uatlib as U  # noqa: E402


def main(argv):
    U.utf8_stdout()
    if len(argv) < 2 or argv[0] in ('-h', '--help'):
        print(__doc__)
        return
    alias, key = argv[0], argv[1]
    run = U.find_run(None, required=False)
    cfg = U.load_config(run)
    v = (U.load_secrets(cfg).get(alias) or {}).get(key)
    if v is None:
        raise SystemExit(f'{alias}.{key} 값이 비밀 파일에 없다')
    v = str(v)
    if '--digits' in argv:
        v = ''.join(c for c in v if c.isdigit())
    if '--mask' in argv:
        d = ''.join(c for c in v if c.isdigit()) or v
        print(f'{d[:3]}-****-{d[-4:]}' if len(d) >= 7 else '****')
        return
    import ui  # noqa: E402 — 같은 폴더의 드라이버(adb·클립보드 설정 공유)
    if all(ord(c) < 128 and c not in ' "\'\\&|;<>()$`' for c in v):
        ui.adb('shell', 'input', 'text', v)
    else:
        ui.paste_into_focused(v)
    print(f'typed {alias}.{key}')


if __name__ == '__main__':
    main(sys.argv[1:])
