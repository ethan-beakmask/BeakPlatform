#!/usr/bin/env python3
"""
BeakPlatform Open Defense 事件接收範例 CLI。

用途：
  當企業自己的分析系統（ELK / SIEM / 自建腳本）判定事件需要列案時，
  可用這支程式把事件送到 BeakPlatform Open Defense intake webhook，
  由平台自動建立資安案件並啟動處置流程。

前置作業：
  1. 到「安全中心 ／ API Key 管理」建立 API Key，scope 必須含 od_intake，
     並列出允許的 source_systems。secret 只會在建立當下顯示一次。
  2. 到「開放防禦 ／ 事件路由設定」建立事件路由規則。
     沒有命中的規則會得到 422 no_mapping。
  3. 路由指到的表單必須已有 Published 版本；webhook 不支援測試模式。

環境變數：
  BP_BASE_URL          平台網址，需包含 /beakplatform 這類 nginx 前綴。
  BP_API_KEY_ID        API Key 的 key_id，例如 ak_xxxxxxxx。
  BP_API_KEY_SECRET    建立 API Key 時取得的一次性 secret。

  secret 刻意只從 BP_API_KEY_SECRET 讀，不提供命令列參數，避免進入 shell
  history 或 ps 輸出。程式任何情況都不會印出 secret。

典型用法：
  逐項參數送一筆：
    export BP_BASE_URL=https://platform.example.com/beakplatform
    export BP_API_KEY_ID=ak_xxxxxxxx
    export BP_API_KEY_SECRET='建立 API Key 時顯示的一次性 secret'
    python3 od_intake_send_event.py --source-system elk --event-class web_activity \\
      --severity 4 --title "SQLi attempt on /login" \\
      --actor-ip 203.0.113.42 --target-host app.example.com

  從 JSON 檔送：
    python3 od_intake_send_event.py --event-file event.json

  dry-run 對帳：
    python3 od_intake_send_event.py --dry-run --source-system elk \\
      --event-class web_activity --severity 4 --title "SQLi attempt on /login" \\
      --actor-ip 203.0.113.42 --target-host app.example.com

這支程式刻意不依賴任何第三方套件，可直接複製到分析主機上使用。

注意：
  平台顯示的 secret 是 base64 urlsafe 字串。簽章前必須先還原成 32 bytes：
    base64.urlsafe_b64decode(secret + '=' * (-len(secret) % 4))
  直接把 base64 字串當 HMAC key 會得到 401 auth_failed。
"""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import socket
import ssl
import sys
import time
import uuid
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


EVENT_CLASSES = (
    "detection_finding",
    "network_activity",
    "web_activity",
    "process_activity",
)

REQUIRE_ACTOR_IP = ("network_activity", "web_activity")
EXIT_USAGE = 1
EXIT_AUTH = 3
EXIT_AUTHZ = 4
EXIT_BAD_EVENT = 5
EXIT_PLATFORM_CONFIG = 6
EXIT_RATE_LIMIT = 7
EXIT_SERVER = 8
EXIT_NETWORK = 9


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_secret_bytes(secret_b64: str) -> bytes:
    try:
        padded = secret_b64 + "=" * (-len(secret_b64) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception:
        raise ValueError("BP_API_KEY_SECRET 不是合法的 base64 urlsafe 字串，請確認使用建立 API Key 時顯示的一次性 secret。")


def sign(secret_b64: str, timestamp: str, body_bytes: bytes) -> str:
    secret = load_secret_bytes(secret_b64)
    canonical = timestamp.encode("ascii") + b"\n" + body_bytes
    digest = hmac.new(secret, canonical, hashlib.sha256).hexdigest()
    return "sha256=" + digest


def require_range(name: str, value: Optional[int], low: int, high: int) -> None:
    if value is not None and (value < low or value > high):
        raise ValueError("%s 必須在 %d 到 %d 之間。" % (name, low, high))


def read_event_file(path: str) -> Dict[str, Any]:
    try:
        if path == "-":
            text = sys.stdin.read()
        else:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
    except OSError as exc:
        raise ValueError("讀取事件 JSON 失敗：%s" % exc)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("事件檔不是合法 JSON：第 %d 行第 %d 欄，%s" % (exc.lineno, exc.colno, exc.msg))
    if not isinstance(data, dict):
        raise ValueError("事件 JSON 必須是 object。")
    return data


def build_event(args: argparse.Namespace) -> Dict[str, Any]:
    if args.event_file:
        return read_event_file(args.event_file)

    missing = []
    for attr, label in (
        ("source_system", "--source-system"),
        ("event_class", "--event-class"),
        ("severity", "--severity"),
        ("title", "--title"),
    ):
        if getattr(args, attr) is None:
            missing.append(label)
    if missing:
        raise ValueError("缺少必要參數：%s。若已有完整 JSON，請改用 --event-file。" % ", ".join(missing))

    require_range("--severity", args.severity, 0, 6)
    require_range("--confidence", args.confidence, 0, 100)

    if args.event_class in REQUIRE_ACTOR_IP and not args.actor_ip:
        raise ValueError("event_class 為 network_activity 或 web_activity 時必須提供 --actor-ip。")

    event = {
        "correlation_id": args.correlation_id or uuid.uuid4().hex,
        "source_system": args.source_system,
        "event_class": args.event_class,
        "occurred_at": args.occurred_at or utc_now_iso(),
        "severity_id": args.severity,
        "finding": {
            "title": args.title,
        },
    }

    if args.confidence is not None:
        event["confidence"] = args.confidence

    finding = event["finding"]
    for key, value in (
        ("summary", args.summary),
        ("rule_id", args.rule_id),
        ("rule_set", args.rule_set),
    ):
        if value is not None:
            finding[key] = value

    actor = {}
    for key, value in (
        ("ip", args.actor_ip),
        ("country", args.actor_country),
        ("asn", args.actor_asn),
        ("user_agent", args.actor_user_agent),
    ):
        if value is not None:
            actor[key] = value
    if actor:
        event["actor"] = actor

    target = {}
    for key, value in (
        ("host", args.target_host),
        ("url", args.target_url),
        ("service", args.target_service),
    ):
        if value is not None:
            target[key] = value
    if target:
        event["target"] = target

    detector_hint = {}
    if args.detector_action is not None:
        detector_hint["action"] = args.detector_action
    if args.detector_ttl_sec is not None:
        detector_hint["ttl_sec"] = args.detector_ttl_sec
    if detector_hint:
        event["detector_hint"] = detector_hint

    return event


def make_body_bytes(event: Dict[str, Any]) -> bytes:
    return json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def endpoint_from_base_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/api/open_defense/intake"


def post_event(endpoint: str, key_id: str, signature: str, timestamp: str,
               body_bytes: bytes, timeout: int, insecure: bool) -> Tuple[int, Dict[str, Any], str]:
    headers = {
        "Content-Type": "application/json",
        "X-BP-Key-Id": key_id,
        "X-BP-Timestamp": timestamp,
        "X-BP-Signature": signature,
    }
    request = urllib.request.Request(endpoint, data=body_bytes, headers=headers, method="POST")
    context = None
    if insecure:
        context = ssl._create_unverified_context()

    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return response.getcode(), parse_json_response(raw), raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, parse_json_response(raw), raw
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        raise ConnectionError("連線失敗、逾時或 DNS 解析失敗：%s" % exc)


def parse_json_response(raw: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}
    if isinstance(parsed, dict):
        return parsed
    return {"_raw": raw}


def explain_error(status: int, payload: Dict[str, Any]) -> Tuple[int, str]:
    error = payload.get("error")
    message = payload.get("message")
    details = payload.get("details")

    lines = ["送出失敗：HTTP %d" % status]
    if error:
        if status == 429:
            lines.append("平台訊息：%s" % error)
        else:
            lines.append("error code：%s" % error)
    if message:
        lines.append("message：%s" % message)
    if isinstance(details, list):
        lines.append("欄位錯誤：")
        for item in details:
            if isinstance(item, dict):
                lines.append("  - %s：%s" % (item.get("field", ""), item.get("error", "")))
            else:
                lines.append("  - %s" % item)
    elif payload.get("_raw"):
        lines.append("平台回應：%s" % payload["_raw"])

    if status == 400:
        code = EXIT_BAD_EVENT
        if error == "invalid_json":
            advice = "建議：body 不是合法 JSON，請修正程式產生的內容；不可重試。"
        else:
            advice = "建議：事件欄位不合 schema，請依 details 逐欄修正；不可重試。"
    elif status == 401:
        code = EXIT_AUTH
        advice = "建議：檢查 secret 是否先做 base64 urlsafe 解碼、主機時鐘是否 NTP 同步、key 是否存在或停用、來源 IP 是否在白名單；不可重試。"
    elif status == 403:
        code = EXIT_AUTHZ
        if error == "scope_denied":
            advice = "建議：到 API Key 管理補上 od_intake scope；不可重試。"
        else:
            advice = "建議：source_system 必須在這把 key 的白名單內，請改用允許名稱或更新 key；不可重試。"
    elif status == 422:
        code = EXIT_PLATFORM_CONFIG
        if error == "form_not_published":
            advice = "建議：路由指到的表單沒有已發行版本，請表單設計者發行；通知平台管理員。"
        else:
            advice = "建議：這個 event_class 沒有命中的事件路由規則，請到事件路由設定新增規則；通知平台管理員。"
    elif status == 429:
        code = EXIT_RATE_LIMIT
        advice = "建議：已觸發限流，請退避後重試。"
    elif 500 <= status <= 599:
        code = EXIT_SERVER
        advice = "建議：平台端內部錯誤，請退避後重試，並通知平台管理員。"
    else:
        code = EXIT_SERVER
        advice = "建議：收到未預期的 HTTP 狀態，請保留輸出並通知平台管理員。"

    lines.append(advice)
    return code, "\n".join(lines)


def print_dry_run(endpoint: str, key_id: str, timestamp: str, signature_value: str,
                  body_bytes: bytes) -> None:
    print("dry-run：未送出 request")
    print("端點：%s" % endpoint)
    print("key_id：%s" % key_id)
    print("timestamp：%s" % timestamp)
    print("簽章 hex：%s" % signature_value[len("sha256="):])
    print("headers（不含 secret）：")
    print("  Content-Type: application/json")
    print("  X-BP-Key-Id: %s" % key_id)
    print("  X-BP-Timestamp: %s" % timestamp)
    print("  X-BP-Signature: %s" % signature_value)
    print("即將送出的 body（下方為美化顯示；實際送出的是未美化的緊湊 bytes）：")
    print(json.dumps(json.loads(body_bytes.decode("utf-8")), ensure_ascii=False, indent=2, sort_keys=True))


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def print_curl(endpoint: str, key_id: str, body_bytes: bytes, insecure: bool) -> None:
    body_text = body_bytes.decode("utf-8")
    curl_insecure = " --insecure" if insecure else ""
    print("")
    print("等價 curl 範例（secret 只讀 $BP_API_KEY_SECRET，不會印出明文）：")
    print("BODY=%s" % shell_quote(body_text))
    print("TS=$(date +%s)")
    print("KEY_HEX=$(printf '%s' \"$BP_API_KEY_SECRET\" | python3 -c 'import base64, sys; s = sys.stdin.read().strip(); s += \"=\" * (-len(s) % 4); print(base64.urlsafe_b64decode(s.encode(\"ascii\")).hex())')")
    print("SIG=$(printf '%s\\n%s' \"$TS\" \"$BODY\" | openssl dgst -sha256 -mac HMAC -macopt hexkey:\"$KEY_HEX\" -hex | awk '{print $NF}')")
    print("curl%s -sS -X POST %s \\" % (curl_insecure, shell_quote(endpoint)))
    print("  -H 'Content-Type: application/json' \\")
    print("  -H %s \\" % shell_quote("X-BP-Key-Id: " + key_id))
    print("  -H \"X-BP-Timestamp: $TS\" \\")
    print("  -H \"X-BP-Signature: sha256=$SIG\" \\")
    print("  --data-binary \"$BODY\"")


class ChineseArgumentParser(argparse.ArgumentParser):
    def format_usage(self) -> str:
        return super().format_usage().replace("usage:", "用法:")

    def format_help(self) -> str:
        return super().format_help().replace("usage:", "用法:")

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, "參數錯誤：%s\n" % message)


def make_parser() -> argparse.ArgumentParser:
    parser = ChineseArgumentParser(
        description="送出 Open Defense intake 事件。無參數執行時只顯示本說明並以 0 結束。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        add_help=False,
    )
    parser._optionals.title = "選項"
    parser.add_argument("-h", "--help", action="help", help="顯示這份說明並結束")
    parser.add_argument("--base-url", default=os.environ.get("BP_BASE_URL"),
                        help="平台網址，必須包含 /beakplatform 這類前綴；未給時讀 BP_BASE_URL")
    parser.add_argument("--key-id", default=os.environ.get("BP_API_KEY_ID"),
                        help="API Key 的 key_id；未給時讀 BP_API_KEY_ID")
    parser.add_argument("--timeout", type=int, default=10, help="連線逾時秒數")
    parser.add_argument("--insecure", action="store_true",
                        help="略過 TLS 憑證驗證，只給自簽憑證的內部測試用")

    source = parser.add_mutually_exclusive_group()
    source.add_argument("--event-file", help="讀一個 JSON 檔當完整 body；給 - 代表從 stdin 讀")
    source.add_argument("--source-system", help="來源系統名稱，必須在 API Key 的白名單內")

    parser.add_argument("--event-class", choices=EVENT_CLASSES,
                        help="事件類型")
    parser.add_argument("--severity", type=int, help="嚴重度，0 到 6")
    parser.add_argument("--title", help="finding.title")
    parser.add_argument("--occurred-at", help="ISO-8601 UTC 字串，未給時使用現在 UTC，格式 %%Y-%%m-%%dT%%H:%%M:%%SZ")
    parser.add_argument("--correlation-id", help="冪等鍵，未給時使用 uuid4 hex")
    parser.add_argument("--actor-ip", help="攻擊者 IP；network_activity / web_activity 必填")
    parser.add_argument("--actor-country", help="攻擊者國家或地區代碼")
    parser.add_argument("--actor-asn", help="攻擊者 ASN")
    parser.add_argument("--actor-user-agent", help="攻擊者 user agent")
    parser.add_argument("--target-host", help="目標主機")
    parser.add_argument("--target-url", help="目標 URL")
    parser.add_argument("--target-service", help="目標服務")
    parser.add_argument("--rule-id", help="偵測規則 ID")
    parser.add_argument("--rule-set", help="偵測規則集")
    parser.add_argument("--summary", help="finding.summary")
    parser.add_argument("--confidence", type=int, help="信心分數，0 到 100")
    parser.add_argument("--detector-action", help="偵測器建議動作")
    parser.add_argument("--detector-ttl-sec", type=int, help="偵測器建議有效秒數")
    parser.add_argument("--dry-run", action="store_true",
                        help="不送出，只印端點、key_id、timestamp、簽章、headers 與 body")
    parser.add_argument("--print-curl", action="store_true",
                        help="另外印出等價 curl 指令；secret 以 $BP_API_KEY_SECRET 表示")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = make_parser()
    args_list = sys.argv[1:] if argv is None else argv
    if not args_list:
        parser.print_help()
        return 0

    args = parser.parse_args(args_list)

    try:
        if not args.base_url:
            raise ValueError("缺少 --base-url 或環境變數 BP_BASE_URL。")
        if not args.key_id:
            raise ValueError("缺少 --key-id 或環境變數 BP_API_KEY_ID。")
        secret = os.environ.get("BP_API_KEY_SECRET")
        if not secret:
            raise ValueError("缺少環境變數 BP_API_KEY_SECRET。secret 不接受命令列參數，避免出現在 shell history 與 ps 輸出。")
        if args.timeout <= 0:
            raise ValueError("--timeout 必須大於 0。")

        event = build_event(args)
        body_bytes = make_body_bytes(event)
        timestamp = str(int(time.time()))
        signature_value = sign(secret, timestamp, body_bytes)
        endpoint = endpoint_from_base_url(args.base_url)

        if args.dry_run:
            print_dry_run(endpoint, args.key_id, timestamp, signature_value, body_bytes)
            if args.print_curl:
                print_curl(endpoint, args.key_id, body_bytes, args.insecure)
            return 0

        status, payload, _raw = post_event(
            endpoint, args.key_id, signature_value, timestamp,
            body_bytes, args.timeout, args.insecure,
        )

        if 200 <= status <= 299 and payload.get("success") is True:
            print("送出成功")
            print("案件識別碼：%s" % payload.get("case_secure_code"))
            print("是否為重複事件：%s" % ("是" if payload.get("duplicate") else "否"))
            workflow_started = payload.get("workflow_started")
            if workflow_started is None:
                workflow_text = "平台未回傳"
            else:
                workflow_text = "是" if workflow_started else "否"
            print("流程是否已啟動：%s" % workflow_text)
            print("可在『開放防禦 ／ 資安案件處置中心』看到此案件。")
            if args.print_curl:
                print_curl(endpoint, args.key_id, body_bytes, args.insecure)
            return 0

        exit_code, text = explain_error(status, payload)
        print(text, file=sys.stderr)
        return exit_code
    except ValueError as exc:
        print("本地設定或參數錯誤：%s" % exc, file=sys.stderr)
        print("建議：請修正參數、環境變數或事件 JSON；不可重試。", file=sys.stderr)
        return EXIT_USAGE
    except ConnectionError as exc:
        print("送出失敗：%s" % exc, file=sys.stderr)
        print("建議：連線失敗、逾時或 DNS 解析失敗，請退避後重試。", file=sys.stderr)
        return EXIT_NETWORK
    except Exception:
        print("發生未預期錯誤；以下 traceback 供排查使用。", file=sys.stderr)
        raise


if __name__ == "__main__":
    sys.exit(main())
