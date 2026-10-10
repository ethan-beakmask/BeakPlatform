#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HttpRequest 節點示範用 mock HTTP server。"""
from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


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
