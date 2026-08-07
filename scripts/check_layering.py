"""檢查 BeakPlatform 架構分層 import 規則。

規則：
    目前檢查平台核心 backend/app 不得反向 import modules 下的業務模組，
    但允許規則定義中的白名單檔案。

Baseline：
    scripts/layering_baseline.json 記錄既有違規的檔案、模組名與次數。
    已知違規不使檢查失敗，新增或超出 baseline 的違規會失敗。

退出碼：
    0 通過，沒有新增違規。
    1 有新增或超出 baseline 的違規。
    2 執行錯誤，例如 Python 檔無法解析或 baseline JSON 格式錯誤。
"""

import argparse
import ast
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = Path("scripts/layering_baseline.json")

RULES = [
    {
        "id": "platform-no-module-import",
        "description": "平台核心不得反向 import 業務模組。",
        "scan_paths": ["backend/app"],
        "forbidden_prefixes": ["modules"],
        "allow_files": ["backend/app/web/dev.py"],
    }
]


class ChineseArgumentParser(argparse.ArgumentParser):
    def format_usage(self):
        return super().format_usage().replace("usage:", "用法:", 1)

    def format_help(self):
        return super().format_help().replace("usage:", "用法:", 1)


def project_relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def display_path(path: Path) -> str:
    """回傳可讀路徑；不在專案內時退回絕對路徑，不得因此中斷流程。"""
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def import_matches_prefix(imported_name: str, prefix: str) -> bool:
    return imported_name == prefix or imported_name.startswith(f"{prefix}.")


def module_group(imported_name: str, prefix: str) -> str:
    remainder = imported_name[len(prefix) :].lstrip(".")
    return remainder.split(".", 1)[0] if remainder else prefix


def source_segment(lines, node):
    segment = ast.get_source_segment("".join(lines), node)
    if segment:
        return " ".join(segment.strip().split())
    if isinstance(node, ast.Import):
        names = ", ".join(
            f"{alias.name} as {alias.asname}" if alias.asname else alias.name
            for alias in node.names
        )
        return f"import {names}"
    if isinstance(node, ast.ImportFrom):
        module = "." * node.level + (node.module or "")
        names = ", ".join(
            f"{alias.name} as {alias.asname}" if alias.asname else alias.name
            for alias in node.names
        )
        return f"from {module} import {names}"
    return "<無法取得 import 敘述>"


def iter_python_files(scan_root: Path):
    if not scan_root.exists():
        raise FileNotFoundError(f"掃描路徑不存在：{project_relative(scan_root)}")
    if not scan_root.is_dir():
        raise NotADirectoryError(f"掃描路徑不是目錄：{project_relative(scan_root)}")

    files = []
    for path in scan_root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        files.append(path)
    return sorted(files)


def scan_rule(rule):
    allow_files = set(rule["allow_files"])
    forbidden_prefixes = rule["forbidden_prefixes"]
    violations = []
    parse_errors = []
    scanned_files = 0

    for scan_path in rule["scan_paths"]:
        for path in iter_python_files(PROJECT_ROOT / scan_path):
            rel_path = project_relative(path)
            if rel_path in allow_files:
                continue
            scanned_files += 1

            try:
                text = path.read_text(encoding="utf-8")
                tree = ast.parse(text, filename=str(path))
            except SyntaxError as exc:
                parse_errors.append(f"{rel_path}:{exc.lineno}: Python 語法錯誤：{exc.msg}")
                continue
            except OSError as exc:
                parse_errors.append(f"{rel_path}: 無法讀取檔案：{exc}")
                continue

            lines = text.splitlines(keepends=True)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level != 0 or not node.module:
                        continue
                    imported_names = [node.module]
                else:
                    continue

                for imported_name in imported_names:
                    for prefix in forbidden_prefixes:
                        if not import_matches_prefix(imported_name, prefix):
                            continue
                        violations.append(
                            {
                                "rule_id": rule["id"],
                                "file_path": rel_path,
                                "line": getattr(node, "lineno", 0),
                                "statement": source_segment(lines, node),
                                "imported_name": imported_name,
                                "module_name": module_group(imported_name, prefix),
                            }
                        )
                        break

    return {
        "scanned_files": scanned_files,
        "violations": sorted(
            violations,
            key=lambda item: (item["file_path"], item["line"], item["module_name"], item["statement"]),
        ),
        "parse_errors": parse_errors,
    }


def merge_scan_results(results):
    return {
        "scanned_files": sum(result["scanned_files"] for result in results),
        "violations": [violation for result in results for violation in result["violations"]],
        "parse_errors": [error for result in results for error in result["parse_errors"]],
    }


def empty_counts_for_rules(rules):
    return {rule["id"]: {} for rule in rules}


def counts_from_violations(rules, violations):
    counts = empty_counts_for_rules(rules)
    for violation in violations:
        file_counts = counts.setdefault(violation["rule_id"], {}).setdefault(violation["file_path"], {})
        module_name = violation["module_name"]
        file_counts[module_name] = file_counts.get(module_name, 0) + 1
    return {
        rule_id: {
            file_path: dict(sorted(module_counts.items()))
            for file_path, module_counts in sorted(file_counts.items())
            if module_counts
        }
        for rule_id, file_counts in sorted(counts.items())
    }


def read_baseline_json(path: Path):
    """讀取 baseline 原始內容（不過濾規則），檔案不存在時回空 dict。

    `--update-baseline` 需要保留本次未選中規則的既有條目，因此不能直接用
    load_baseline 的過濾結果覆寫檔案。
    """
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"baseline JSON 格式錯誤：{display_path(path)}:{exc.lineno}:{exc.colno}: {exc.msg}")
    except OSError as exc:
        raise ValueError(f"無法讀取 baseline：{display_path(path)}：{exc}")

    if not isinstance(raw, dict):
        raise ValueError("baseline JSON 最外層必須是物件")
    return raw


def load_baseline(path: Path, rules):
    raw = read_baseline_json(path)
    if not raw:
        return empty_counts_for_rules(rules)

    baseline = empty_counts_for_rules(rules)
    selected_rule_ids = set(baseline)
    for rule_id, file_map in raw.items():
        if rule_id not in selected_rule_ids:
            continue
        if not isinstance(rule_id, str) or not isinstance(file_map, dict):
            raise ValueError("baseline 格式錯誤：規則 id 必須對應到檔案物件")
        normalized_file_map = {}
        for file_path, module_map in file_map.items():
            if not isinstance(file_path, str) or not isinstance(module_map, dict):
                raise ValueError(f"baseline 格式錯誤：{rule_id} 的檔案項目必須是物件")
            normalized_module_map = {}
            for module_name, count in module_map.items():
                if not isinstance(module_name, str) or not isinstance(count, int) or count < 0:
                    raise ValueError(
                        f"baseline 格式錯誤：{rule_id} / {file_path} 的模組次數必須是非負整數"
                    )
                if count:
                    normalized_module_map[module_name] = count
            if normalized_module_map:
                normalized_file_map[file_path] = dict(sorted(normalized_module_map.items()))
        baseline[rule_id] = dict(sorted(normalized_file_map.items()))
    return baseline


def compare_with_baseline(counts, baseline, violations):
    new_violations = []
    resolved = []

    actual_lookup = {
        (violation["rule_id"], violation["file_path"], violation["module_name"]): violation
        for violation in violations
    }

    for rule_id, file_counts in counts.items():
        baseline_rule = baseline.get(rule_id, {})
        for file_path, module_counts in file_counts.items():
            for module_name, actual_count in module_counts.items():
                baseline_count = baseline_rule.get(file_path, {}).get(module_name, 0)
                if actual_count > baseline_count:
                    violation = actual_lookup[(rule_id, file_path, module_name)]
                    new_violations.append(
                        {
                            "rule_id": rule_id,
                            "file_path": file_path,
                            "line": violation["line"],
                            "statement": violation["statement"],
                            "module_name": module_name,
                            "baseline_count": baseline_count,
                            "actual_count": actual_count,
                            "kind": "new_file" if file_path not in baseline_rule else "exceeds_baseline",
                        }
                    )

    for rule_id, baseline_rule in baseline.items():
        actual_rule = counts.get(rule_id, {})
        for file_path, module_counts in baseline_rule.items():
            for module_name, baseline_count in module_counts.items():
                actual_count = actual_rule.get(file_path, {}).get(module_name, 0)
                if actual_count < baseline_count:
                    resolved.append(
                        {
                            "rule_id": rule_id,
                            "file_path": file_path,
                            "module_name": module_name,
                            "baseline_count": baseline_count,
                            "actual_count": actual_count,
                        }
                    )

    return (
        sorted(new_violations, key=lambda item: (item["file_path"], item["line"], item["module_name"])),
        sorted(resolved, key=lambda item: (item["file_path"], item["module_name"])),
    )


def select_rules(rule_ids):
    if not rule_ids:
        return RULES
    known = {rule["id"]: rule for rule in RULES}
    missing = [rule_id for rule_id in rule_ids if rule_id not in known]
    if missing:
        raise ValueError(f"未知規則 id：{', '.join(missing)}")
    return [known[rule_id] for rule_id in rule_ids]


def write_baseline(path: Path, counts):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(counts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"無法寫入 baseline：{display_path(path)}：{exc}")


def build_payload(rules, scan_result, counts, baseline):
    new_violations, resolved = compare_with_baseline(counts, baseline, scan_result["violations"])
    return {
        "ok": not new_violations and not scan_result["parse_errors"],
        "summary": {
            "scanned_files": scan_result["scanned_files"],
            "rules": len(rules),
            "new_violations": len(new_violations),
            "resolved": len(resolved),
        },
        "new_violations": new_violations,
        "resolved": resolved,
        "counts": counts,
        "parse_errors": scan_result["parse_errors"],
    }


def print_human_report(payload, rules):
    print("架構分層檢查報告")
    print("套用規則：")
    for rule in rules:
        print(f"- {rule['id']}：{rule['description']}")

    if payload["parse_errors"]:
        print("\n執行錯誤：")
        for error in payload["parse_errors"]:
            print(f"- {error}")

    if payload["new_violations"]:
        print("\n新增違規：")
        for item in payload["new_violations"]:
            if item["baseline_count"] == 0 and item["kind"] == "new_file":
                reason = "全新檔案的違規"
            else:
                reason = (
                    "既有檔案超出基準的違規"
                    f"（baseline {item['baseline_count']} → 實際 {item['actual_count']}）"
                )
            print(f"- {item['file_path']}:{item['line']}  {item['statement']}  {reason}")
    else:
        print("\n新增違規：無")

    if payload["resolved"]:
        print("\n已收斂：")
        for item in payload["resolved"]:
            print(
                f"- {item['file_path']} / {item['module_name']}："
                f"baseline {item['baseline_count']} → 實際 {item['actual_count']}，"
                "建議跑 --update-baseline"
            )

    summary = payload["summary"]
    print(
        "\n總結："
        f"掃描檔案數 {summary['scanned_files']}，"
        f"規則數 {summary['rules']}，"
        f"新違規數 {summary['new_violations']}，"
        f"已收斂數 {summary['resolved']}"
    )
    print("提示：--help 可查看全部選項")


def print_update_summary(old, new, baseline_path: Path):
    old_total = sum(
        count
        for file_counts in old.values()
        for module_counts in file_counts.values()
        for count in module_counts.values()
    )
    new_total = sum(
        count
        for file_counts in new.values()
        for module_counts in file_counts.values()
        for count in module_counts.values()
    )
    old_pairs = sum(len(module_counts) for file_counts in old.values() for module_counts in file_counts.values())
    new_pairs = sum(len(module_counts) for file_counts in new.values() for module_counts in file_counts.values())
    print(f"已更新 baseline：{display_path(baseline_path)}")
    print(f"違規組合數：{old_pairs} → {new_pairs}")
    print(f"違規總次數：{old_total} → {new_total}")


def parse_args(argv):
    parser = ChineseArgumentParser(
        description="檢查 BeakPlatform 架構分層規則，預設會執行檢查並輸出人類可讀報告。",
        add_help=False,
    )
    parser._optionals.title = "選項"
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        help="顯示此說明文字後結束。",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="以目前掃描結果覆寫 baseline 檔，印出變更摘要後結束。",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 輸出結果到 stdout，供 CI 或其他工具消費。",
    )
    parser.add_argument(
        "--baseline",
        default=DEFAULT_BASELINE.as_posix(),
        help="指定 baseline 檔路徑，預設為 scripts/layering_baseline.json。",
    )
    parser.add_argument(
        "--rule",
        action="append",
        dest="rule_ids",
        help="只跑指定規則 id，可重複指定；不給則跑全部規則。",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    try:
        rules = select_rules(args.rule_ids)
        baseline_path = Path(args.baseline)
        if not baseline_path.is_absolute():
            baseline_path = PROJECT_ROOT / baseline_path

        scan_result = merge_scan_results([scan_rule(rule) for rule in rules])
        if scan_result["parse_errors"]:
            for error in scan_result["parse_errors"]:
                print(f"警告：{error}", file=sys.stderr)
            payload = build_payload(
                rules,
                scan_result,
                counts_from_violations(rules, scan_result["violations"]),
                empty_counts_for_rules(rules),
            )
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print_human_report(payload, rules)
            return 2

        counts = counts_from_violations(rules, scan_result["violations"])
        old_baseline = load_baseline(baseline_path, rules)

        if args.update_baseline:
            # 只覆寫本次選中的規則，未選中規則的既有條目原樣保留
            merged = read_baseline_json(baseline_path)
            merged.update(counts)
            write_baseline(baseline_path, merged)
            if not args.json:
                print_update_summary(old_baseline, counts, baseline_path)
            else:
                print(
                    json.dumps(
                        {
                            "updated": True,
                            "baseline": display_path(baseline_path),
                            "counts": counts,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            return 0

        payload = build_payload(rules, scan_result, counts, old_baseline)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_human_report(payload, rules)
        return 1 if payload["new_violations"] else 0
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
