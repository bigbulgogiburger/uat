#!/usr/bin/env python
"""외부 발송 차단용 로컬 수신기 — HTTP(알림톡·SMS·푸시 게이트웨이 흉내)와 SMTP 를 받고 전부 성공으로 답한다.

서버가 실제 고객·협력사에게 문자·메일을 보내는 코드 경로를 그대로 타되, 외부로는 한 통도 나가지 않게 한다.
측정 대상 서버의 발송 base URL·SMTP 호스트를 이 수신기로 바꿔 띄운다(프로젝트 설정 — references/environment.md §3).
본문(전화번호·이름·메시지)과 인증 정보는 기록하지 않는다 — 시각·메서드·경로·크기만 남긴다.

  python sink.py [--http 18080] [--smtp 2525] [--log RUN/work/sink.log] [--rules rules.json]

rules.json(선택) — 경로별 응답 본문. 위에서부터 첫 번째로 match(정규식)가 맞는 규칙을 쓴다. 없으면 {"result":"ok"}.
  [{"match": "/getToken$", "status": 200, "body": {"token": "stub", "expireDate": "2099-12-31 23:59:59"}},
   {"match": "/send", "body": [{"result": "Y", "code": "0000"}]}]
⚠️ 오래 사는 터미널(별도 pane)에서 띄운다 — 에이전트 세션의 백그라운드 작업은 메모리가 모자라면 정리된다.
"""
import argparse
import json
import re
import socketserver
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import uatlib as U  # noqa: E402

LOG = None
RULES = []
CFG = dict(U.CONFIG_DEFAULTS)


def safe_path(path):
    """경로에도 번호·토큰이 실릴 수 있다(예: /users/<번호>) — 비밀 값·redact 패턴·긴 숫자열을 가린다."""
    p = U.mask(path.split('?')[0], CFG)
    return re.sub(r'\d{8,}', '<digits>', p)


def log(msg):
    line = time.strftime('%Y-%m-%d %H:%M:%S ') + msg
    print(line, flush=True)
    if LOG:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')


class Http(BaseHTTPRequestHandler):
    def _reply(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n:
            self.rfile.read(n)
        status, body = 200, {'result': 'ok'}
        for r in RULES:
            if re.search(r['match'], self.path):
                status, body = int(r.get('status', 200)), r.get('body', body)
                break
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        log(f'HTTP {self.command} {safe_path(self.path)} in={n}B -> {status}')

    do_POST = do_PUT = do_GET = do_PATCH = do_DELETE = _reply

    def log_message(self, *args):
        pass


class Smtp(socketserver.StreamRequestHandler):
    def handle(self):
        w = lambda s: self.wfile.write((s + '\r\n').encode())
        w('220 uat-sink ESMTP')
        rcpt, size, in_data = 0, 0, False
        while True:
            line = self.rfile.readline()
            if not line:
                break
            if in_data:
                if line in (b'.\r\n', b'.\n'):
                    in_data = False
                    w('250 OK queued')
                    log(f'SMTP message rcpt={rcpt} size={size}B')
                    rcpt, size = 0, 0
                else:
                    size += len(line)
                continue
            cmd = line.decode(errors='replace').strip().upper()
            if cmd.startswith(('EHLO', 'HELO')):
                w('250-uat-sink')
                w('250-AUTH PLAIN LOGIN')
                w('250 OK')
            elif cmd.startswith('AUTH'):
                w('235 OK')            # 자격 증명은 읽지 않는다
            elif cmd.startswith('MAIL'):
                w('250 OK')
            elif cmd.startswith('RCPT'):
                rcpt += 1
                w('250 OK')
            elif cmd == 'DATA':
                in_data = True
                w('354 end with .')
            elif cmd == 'QUIT':
                w('221 bye')
                break
            else:
                w('250 OK')


class ThreadingTCP(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    global LOG, RULES, CFG
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--http', type=int, default=18080)
    p.add_argument('--smtp', type=int, default=2525)
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--log')
    p.add_argument('--rules')
    p.add_argument('--config', help='프로필(비밀 값·redact 패턴으로 로그 경로를 가린다) — 없으면 UAT_CONFIG')
    a = p.parse_args()
    LOG = a.log
    try:
        CFG = U.load_config(U.find_run(None, required=False), a.config)
    except SystemExit:
        pass  # 프로필 없이도 뜬다 — 기본 redact 패턴만 쓴다
    if a.rules:
        RULES = json.load(open(a.rules, encoding='utf-8'))
    if a.smtp:
        srv = ThreadingTCP((a.host, a.smtp), Smtp)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f'sink up http={a.http} smtp={a.smtp} host={a.host} rules={len(RULES)}')
    ThreadingHTTPServer((a.host, a.http), Http).serve_forever()


if __name__ == '__main__':
    main()
