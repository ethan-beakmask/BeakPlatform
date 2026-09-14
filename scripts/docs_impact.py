#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""docs_impact -- 版控影響分析：程式改了，哪些使用者文件要跟著複查

讀取 docs/ 下每份文件 frontmatter 的 covers 欄位（程式路徑 glob），
比對兩個 git 版本之間的檔案異動，回答兩個問題：

  1. 這次改動影響哪些文件？（文件可能已過期，需要人複查）
  2. 哪些改動的程式沒有任何文件覆蓋？（可能缺文件，或本來就不需要）

不依賴 mkdocs build，直接掃 md 檔，可獨立在 pre-push hook 或 CI 執行。

用法範例：
  docs_impact.py --docs docs --base HEAD~1
  docs_impact.py --docs docs --base origin/master --head HEAD --format json
  docs_impact.py --docs docs --base v1.2.0 --fail-on-impact   # CI：有影響就 exit 1
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

_FM_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)
_H1_RE = re.compile(r'^#\s+(.+?)\s*$', re.MULTILINE)


def glob_to_regex(pattern: str) -> re.Pattern:
    """把 covers 的 glob 轉成 regex。

    ** 跨目錄、* 不跨目錄、? 單一字元。目錄型 pattern（結尾是 /）視同 /**。
    """
    if pattern.endswith('/'):
        pattern += '**'
    out = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == '*':
            if pattern[i:i + 2] == '**':
                out.append('.*')
                i += 2
                if pattern[i:i + 1] == '/':
                    i += 1
                continue
            out.append('[^/]*')
        elif c == '?':
            out.append('[^/]')
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile('^' + ''.join(out) + '$')


def load_docs(docs_dir: Path) -> list[dict]:
    """掃出所有帶 covers 的文件。"""
    docs = []
    for md in sorted(docs_dir.rglob('*.md')):
        try:
            raw = md.read_text(encoding='utf-8')
        except OSError:
            continue
        m = _FM_RE.match(raw)
        if not m:
            continue
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            print(f'警告：{md} 的 frontmatter 無法解析，已略過', file=sys.stderr)
            continue
        covers = meta.get('covers') or []
        if isinstance(covers, str):
            covers = [covers]
        if not covers:
            continue
        h1 = _H1_RE.search(raw[m.end():])
        docs.append({
            'path': str(md),
            'title': meta.get('title') or (h1.group(1) if h1 else md.name),
            'audience': meta.get('audience', ''),
            'covers': covers,
            'matchers': [(c, glob_to_regex(c)) for c in covers],
        })
    return docs


def changed_files(repo: Path, base: str, head: str) -> list[str]:
    cmd = ['git', '-C', str(repo), 'diff', '--name-only', f'{base}..{head}']
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        sys.exit('錯誤：找不到 git 指令')
    except subprocess.CalledProcessError as e:
        sys.exit(f'錯誤：git diff 失敗（{base}..{head}）\n{e.stderr.strip()}')
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def tracked_files(repo: Path) -> list[str]:
    r = subprocess.run(['git', '-C', str(repo), 'ls-files'],
                       capture_output=True, text=True, check=True)
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def verify_covers(docs: list[dict], repo: Path) -> int:
    """檢查每個 covers pattern 在 repo 裡是否真的匹配得到檔案。

    程式改名或搬家時 covers 會靜默失效——影響分析從此永遠回報「無影響」，
    比沒有這套機制更危險。這個檢查要進 CI。
    """
    all_files = tracked_files(repo)
    dead = []
    for d in docs:
        for pattern, rx in d['matchers']:
            if not any(rx.match(f) for f in all_files):
                dead.append((d['path'], pattern))

    total = sum(len(d['matchers']) for d in docs)
    print(f'檢查 {len(docs)} 份文件、{total} 條 covers 宣告，'
          f'比對 {len(all_files)} 個版控檔案')
    print()
    if not dead:
        print('全部 covers 宣告都有對應的實際檔案。')
        return 0
    print(f'失效的 covers 宣告（{len(dead)} 條，比對不到任何檔案）：')
    print()
    for path, pattern in dead:
        print(f'  {path}')
        print(f'    covers: {pattern}')
    print()
    print('程式可能已改名或搬移，請更新文件的 covers 欄位。')
    return 1


def analyse(docs: list[dict], files: list[str]) -> dict:
    impacted: dict[str, dict] = {}
    covered = set()
    for f in files:
        for d in docs:
            for pattern, rx in d['matchers']:
                if rx.match(f):
                    covered.add(f)
                    e = impacted.setdefault(d['path'], {
                        'title': d['title'],
                        'audience': d['audience'],
                        'triggers': [],
                    })
                    e['triggers'].append({'file': f, 'pattern': pattern})
                    break
    return {
        'changed_total': len(files),
        'impacted_docs': impacted,
        'uncovered_files': sorted(set(files) - covered),
    }


def print_text(result: dict, base: str, head: str, show_uncovered: bool) -> None:
    docs = result['impacted_docs']
    print(f'比較範圍：{base}..{head}　異動檔案 {result["changed_total"]} 個')
    print()
    if not docs:
        print('沒有任何使用者文件受本次異動影響。')
    else:
        print(f'需要複查的文件（{len(docs)} 份）：')
        print()
        for path, info in sorted(docs.items()):
            aud = f'　[{info["audience"]}]' if info['audience'] else ''
            print(f'  {path}{aud}')
            print(f'    {info["title"]}')
            for t in info['triggers'][:5]:
                print(f'      ← {t["file"]}　（命中 covers: {t["pattern"]}）')
            if len(info['triggers']) > 5:
                print(f'      ← 另有 {len(info["triggers"]) - 5} 個檔案')
            print()
    if show_uncovered and result['uncovered_files']:
        print(f'未被任何文件覆蓋的異動檔案（{len(result["uncovered_files"])} 個）：')
        for f in result['uncovered_files'][:40]:
            print(f'  {f}')
        if len(result['uncovered_files']) > 40:
            print(f'  ...另有 {len(result["uncovered_files"]) - 40} 個')


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='docs_impact.py',
        description='版控影響分析：依 frontmatter 的 covers 欄位，'
                    '找出因程式異動而需要複查的使用者文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='範例：\n'
               '  docs_impact.py --docs docs --base HEAD~1\n'
               '  docs_impact.py --docs docs --base origin/master --format json\n'
               '  docs_impact.py --docs docs --base v1.2.0 --fail-on-impact\n',
    )
    p.add_argument('--repo', default='.', help='git 倉庫路徑（預設：目前目錄）')
    p.add_argument('--docs', default='docs', help='文件目錄（預設：docs）')
    p.add_argument('--base', default='HEAD~1', help='比較基準版本（預設：HEAD~1）')
    p.add_argument('--head', default='HEAD', help='比較目標版本（預設：HEAD）')
    p.add_argument('--format', choices=['text', 'json'], default='text',
                   help='輸出格式（預設：text）')
    p.add_argument('--show-uncovered', action='store_true',
                   help='一併列出未被任何文件覆蓋的異動檔案')
    p.add_argument('--fail-on-impact', action='store_true',
                   help='有文件受影響時以 exit code 1 結束，供 CI 阻擋用')
    p.add_argument('--verify-covers', action='store_true',
                   help='只檢查 covers 宣告是否還對得到實際檔案（不做版本比較），'
                        '有失效宣告時 exit code 1')
    return p


def main(argv: list[str]) -> int:
    parser = build_parser()
    if not argv:
        parser.print_help()
        return 0
    args = parser.parse_args(argv)

    docs_dir = Path(args.docs)
    if not docs_dir.is_dir():
        sys.exit(f'錯誤：文件目錄不存在：{docs_dir}')

    docs = load_docs(docs_dir)
    if not docs:
        sys.exit(f'錯誤：{docs_dir} 下沒有任何宣告 covers 的文件')

    if args.verify_covers:
        return verify_covers(docs, Path(args.repo))

    files = changed_files(Path(args.repo), args.base, args.head)
    result = analyse(docs, files)

    if args.format == 'json':
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_text(result, args.base, args.head, args.show_uncovered)

    return 1 if (args.fail_on_impact and result['impacted_docs']) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
