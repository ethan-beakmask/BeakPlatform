#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BeakPlatform 表單 API 建單工具。

secret 是安全中心建立 API Key 時只顯示一次的 base64url 字串；本工具會先解碼成
raw bytes 再做 HMAC，請把 UI 顯示的值原樣提供給 --secret 或 BP_SECRET。
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request


EXIT_ARGS = 2
EXIT_PLATFORM = 3
EXIT_CONNECT = 4


def decode_secret(secret_text):
    s = (secret_text or '').strip()
    s += '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode('ascii'))


def compute_request_signature(secret, timestamp, body):
    canonical = timestamp.encode('ascii') + b'\n' + body
    return 'sha256=' + hmac.new(secret, canonical, hashlib.sha256).hexdigest()


def call_platform(base, key_id, secret, method, path, body=None, bad_signature=False):
    raw = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode('utf-8') if body is not None else b''
    ts = str(int(time.time()))
    sig = 'sha256=' + ('0' * 64) if bad_signature else compute_request_signature(secret, ts, raw)

    req = urllib.request.Request(
        base.rstrip('/') + path,
        data=(raw if body is not None else None),
        method=method,
    )
    req.add_header('X-BP-Key-Id', key_id)
    req.add_header('X-BP-Timestamp', ts)
    req.add_header('X-BP-Signature', sig)
    if body is not None:
        req.add_header('Content-Type', 'application/json')

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, parse_json(resp.read())
    except urllib.error.HTTPError as exc:
        payload = exc.read() or b'{}'
        return exc.code, parse_json(payload)
    except urllib.error.URLError as exc:
        print(f'連線失敗：{exc.reason}', file=sys.stderr)
        raise SystemExit(EXIT_CONNECT)


def parse_json(payload):
    try:
        return json.loads(payload or b'{}')
    except ValueError:
        return {'_raw': (payload or b'').decode('utf-8', 'replace')[:800]}


def print_result(summary, status, data):
    print(f'{summary}（HTTP {status}）')
    print(json.dumps(data, ensure_ascii=False, indent=2))


def parse_fields(items):
    result = {}
    for item in items or []:
        if '=' not in item:
            raise ValueError(f'--field 要寫成 KEY=VALUE，收到 {item!r}')
        key, value = item.split('=', 1)
        if not key:
            raise ValueError('--field 的 KEY 不可空白')
        result[key] = value
    return result


def parse_json_object(text):
    if not text:
        return {}
    try:
        value = json.loads(text)
    except ValueError as exc:
        raise ValueError(f'--json 不是合法 JSON：{exc}') from exc
    if not isinstance(value, dict):
        raise ValueError('--json 必須是一個 JSON 物件')
    return value


def build_parser():
    parser = argparse.ArgumentParser(
        description='用 HMAC API Key 呼叫 BeakPlatform，列表單或建立一張資安案件單',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""範例：
  BP_BASE_URL=http://<平台IP>:8000/beakplatform BP_KEY_ID=ak_xxx BP_SECRET=<base64url> \\
      %(prog)s --list
  BP_BASE_URL=http://<平台IP>:8000/beakplatform BP_KEY_ID=ak_xxx BP_SECRET=<base64url> \\
      %(prog)s --form-code SEC_INCIDENT_RESPONSE --subject 'TEST-弱點通報' \\
      --field finding_title='TEST-弱點通報' --field source_system=manual --field severity_id=3

退出碼：0 成功、2 參數錯、3 平台回非 2xx、4 連線失敗
注意：secret 是 base64url，工具會自己解碼後簽章；不要先自行轉碼。""")
    parser.add_argument('--base', default=os.getenv('BP_BASE_URL'), help='平台位址，需含 /beakplatform；也可用 BP_BASE_URL')
    parser.add_argument('--key-id', default=os.getenv('BP_KEY_ID'), help='API Key 的 key_id；也可用 BP_KEY_ID')
    parser.add_argument('--secret', default=os.getenv('BP_SECRET'), help='API Key secret 的 base64url 字串；也可用 BP_SECRET')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--list', action='store_true', help='列出這把 key 可發動的表單')
    group.add_argument('--form-code', metavar='CODE', help='用 form_code 建立表單案件')
    group.add_argument('--selftest', metavar='FORM_CODE', help='用 form_code 跑四項連線/錯誤行為驗證')
    parser.add_argument('--subject', default='', help='表單主旨；使用 --form-code 時必填')
    parser.add_argument('--field', action='append', default=[], metavar='KEY=VALUE', help='表單欄位，可重複')
    parser.add_argument('--json', default='', help='整包 form_data JSON 物件，會與 --field 合併')
    return parser


def require_connection_args(args):
    missing = []
    if not args.base:
        missing.append('--base 或 BP_BASE_URL')
    if not args.key_id:
        missing.append('--key-id 或 BP_KEY_ID')
    if not args.secret:
        missing.append('--secret 或 BP_SECRET')
    if missing:
        print('參數錯誤：缺少 ' + '、'.join(missing), file=sys.stderr)
        return False
    return True


def build_form_data(args):
    form_data = parse_json_object(args.json)
    form_data.update(parse_fields(args.field))
    return form_data


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not argv:
        parser.print_help(sys.stderr)
        return 1
    args = parser.parse_args(argv)
    if not require_connection_args(args):
        return EXIT_ARGS

    try:
        secret = decode_secret(args.secret)
    except Exception:
        print('參數錯誤：--secret / BP_SECRET 不是合法的 base64url 字串', file=sys.stderr)
        return EXIT_ARGS

    try:
        if args.list:
            status, data = call_platform(args.base, args.key_id, secret, 'GET', '/api/trigger/forms')
            print_result('列出可發動表單成功' if status == 200 else '列出可發動表單失敗', status, data)
            return 0 if 200 <= status < 300 else EXIT_PLATFORM

        if args.form_code:
            if not args.subject:
                print('參數錯誤：--form-code 需要同時提供 --subject', file=sys.stderr)
                return EXIT_ARGS
            form_data = build_form_data(args)
            payload = {'form_code': args.form_code, 'subject': args.subject, 'form_data': form_data}
            status, data = call_platform(args.base, args.key_id, secret, 'POST', '/api/trigger/form', payload)
            print_result('建單成功' if 200 <= status < 300 else '建單失敗', status, data)
            return 0 if 200 <= status < 300 else EXIT_PLATFORM

        return run_selftest(args.base, args.key_id, secret, args.selftest)
    except ValueError as exc:
        print(f'參數錯誤：{exc}', file=sys.stderr)
        return EXIT_ARGS


def run_selftest(base, key_id, secret, form_code):
    print(f'自我測試：base={base}  key={key_id}  form_code={form_code}')
    st1, data1 = call_platform(base, key_id, secret, 'GET', '/api/trigger/forms')
    print_result('1/4 列出可發動表單，期望 200', st1, data1)

    st2, data2 = call_platform(base, key_id, secret, 'POST', '/api/trigger/form', {
        'form_code': form_code,
        'subject': f'selftest unknown field {int(time.time())}',
        'form_data': {'__unknown_probe__': 'x'},
    })
    print_result('2/4 未知欄位，期望 400 unknown_field', st2, data2)

    st3, data3 = call_platform(base, key_id, secret, 'POST', '/api/trigger/form', {
        'form_code': 'ZZZZ_NOT_EXIST_FORM_CODE',
        'subject': 'selftest not found',
        'form_data': {},
    })
    print_result('3/4 不存在或 scope 外表單，期望 404 form_not_found', st3, data3)

    st4, data4 = call_platform(base, key_id, secret, 'POST', '/api/trigger/form', {
        'form_code': form_code,
        'subject': 'selftest bad signature',
        'form_data': {},
    }, bad_signature=True)
    print_result('4/4 錯誤簽章，期望 401 auth_failed', st4, data4)

    expected = [(st1, 200), (st2, 400), (st3, 404), (st4, 401)]
    ok = all(actual == want for actual, want in expected)
    if ok:
        print('四項全部符合預期')
        return 0
    print('有項目不符預期：' + '，'.join(f'實際 {actual} 期望 {want}' for actual, want in expected if actual != want))
    return EXIT_PLATFORM


if __name__ == '__main__':
    sys.exit(main())
