#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HttpRequest 節點示範用 mock HTTP server。"""
from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


class Handler(BaseHTTPRequestHandler):
    server_version = 'BeakHttpMock/1'

    def log_message(self, fmt, *args):
        print('%s - %s' % (self.address_string(), fmt % args), flush=True)

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/ping':
            self._send_json(200, {'pong': True, 'path': parsed.path})
            return
        if parsed.path.startswith('/status/'):
            try:
                status = int(parsed.path.rsplit('/', 1)[1])
            except ValueError:
                status = 400
            self._send_json(status, {'status': status})
            return
        if parsed.path == '/slow':
            seconds = int(parse_qs(parsed.query).get('seconds', ['1'])[0])
            time.sleep(max(0, min(30, seconds)))
            self._send_json(200, {'slow': seconds})
            return
        self._send_json(404, {'error': 'not_found'})

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(length) if length else b''
        if parsed.path == '/callback-later':
            try:
                payload = json.loads(raw.decode('utf-8') or '{}')
            except ValueError:
                self._send_json(400, {'error': 'invalid_json'})
                return
            callback_url = str(payload.get('callback_url') or '')
            callback_payload = payload.get('payload') if isinstance(payload.get('payload'), dict) else {}
            try:
                delay_seconds = int(payload.get('delay_seconds') or 0)
            except (TypeError, ValueError):
                delay_seconds = 0
            delay_seconds = max(0, min(300, delay_seconds))

            def fire_callback():
                time.sleep(delay_seconds)
                body = json.dumps(callback_payload, ensure_ascii=False).encode('utf-8')
                req = Request(callback_url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
                try:
                    with urlopen(req, timeout=10) as resp:
                        status = resp.getcode()
                        resp_body = resp.read(300).decode('utf-8', errors='replace')
                except Exception as exc:
                    print(f'callback-later error url={callback_url} error={exc}', flush=True)
                    return
                print(f'callback-later posted url={callback_url} status={status} body={resp_body}', flush=True)

            threading.Thread(target=fire_callback, daemon=True).start()
            self._send_json(202, {'accepted': True, 'delay_seconds': delay_seconds})
            return
        if parsed.path == '/echo':
            try:
                payload = json.loads(raw.decode('utf-8') or '{}')
            except ValueError:
                payload = {'raw': raw.decode('utf-8', errors='replace')}
            self._send_json(200, {'echo': payload})
            return
        self._send_json(404, {'error': 'not_found'})


def main():
    parser = argparse.ArgumentParser(description='啟動 HttpRequest 節點示範用 mock HTTP server')
    parser.add_argument('--host', default='127.0.0.1', help='監聽位址（預設 127.0.0.1）')
    parser.add_argument('--port', type=int, default=8089, help='監聽埠（預設 8089）')
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'HttpRequest mock server listening on http://{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
