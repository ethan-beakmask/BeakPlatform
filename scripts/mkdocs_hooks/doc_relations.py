# -*- coding: utf-8 -*-
"""MkDocs hook -- 文件關係處理

處理三個 frontmatter 欄位，這是 MkDocs 沒有原生機制、必須自己補的部分：

  requires: [doc_id, ...]   本頁作業開始前，必須先完成的其他頁
  produces: [資料名, ...]    本頁作業完成後產出、可供其他流程使用的資料
  covers:   [glob, ...]      本頁對應的程式路徑（給 scripts/docs_impact.py 反查用）

build 期間自動做三件事：
  1. 頁首插入「開始前必須先完成」admonition（依 requires 展開，附產出資料）
  2. 頁尾插入「本頁產出的資料，後續由這些流程使用」（requires 的反向索引）
  3. 把 <!-- DEP_GRAPH --> 佔位符換成全站流程依賴 Mermaid 圖

另在 site_dir 產出 doc_map.json，供版控影響分析腳本使用。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml

_FM_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)
_H1_RE = re.compile(r'^#\s+(.+?)\s*$', re.MULTILINE)

# doc_id -> {title, requires, produces, covers, src_uri}
_INDEX: dict[str, dict] = {}
# doc_id -> [依賴它的 doc_id]
_DEPENDENTS: dict[str, list[str]] = {}


def _doc_id(src_uri: str) -> str:
    return src_uri[:-3] if src_uri.endswith('.md') else src_uri


def _as_list(v) -> list[str]:
    if not v:
        return []
    return [str(x) for x in v] if isinstance(v, list) else [str(v)]


def on_files(files, config):
    """先掃過所有頁面的 frontmatter，建立正向與反向索引。"""
    _INDEX.clear()
    _DEPENDENTS.clear()

    for f in files:
        if not f.src_uri.endswith('.md'):
            continue
        try:
            raw = Path(f.abs_src_path).read_text(encoding='utf-8')
        except OSError:
            continue

        m = _FM_RE.match(raw)
        meta = {}
        if m:
            try:
                meta = yaml.safe_load(m.group(1)) or {}
            except yaml.YAMLError:
                meta = {}

        body = raw[m.end():] if m else raw
        h1 = _H1_RE.search(body)
        title = meta.get('title') or (h1.group(1) if h1 else f.src_uri)

        did = _doc_id(f.src_uri)
        _INDEX[did] = {
            'title': title,
            'requires': _as_list(meta.get('requires')),
            'produces': _as_list(meta.get('produces')),
            'covers': _as_list(meta.get('covers')),
            'audience': meta.get('audience', ''),
            'src_uri': f.src_uri,
        }

    for did, info in _INDEX.items():
        for dep in info['requires']:
            _DEPENDENTS.setdefault(dep, []).append(did)

    return files


def _rel_link(from_uri: str, to_did: str) -> str:
    """算出頁對頁的相對 md 連結，交給 MkDocs 自己轉成 html 路徑。"""
    to_uri = _INDEX[to_did]['src_uri'] if to_did in _INDEX else to_did + '.md'
    rel = os.path.relpath(to_uri, os.path.dirname(from_uri))
    return rel.replace(os.sep, '/')


def _prereq_block(did: str, src_uri: str) -> str:
    reqs = _INDEX[did]['requires']
    if not reqs:
        return ''
    lines = ['!!! warning "開始前必須先完成"', '']
    for r in reqs:
        if r in _INDEX:
            produced = _INDEX[r]['produces']
            tail = f'　→ 產出：{"、".join(produced)}' if produced else ''
            lines.append(
                f'    - [{_INDEX[r]["title"]}]({_rel_link(src_uri, r)}){tail}'
            )
        else:
            # 宣告了不存在的前置頁，build 時就要看得見，不要靜默略過
            lines.append(f'    - **（缺文件）`{r}`**')
    return '\n'.join(lines) + '\n\n'


def _followup_block(did: str, src_uri: str) -> str:
    deps = _DEPENDENTS.get(did, [])
    produces = _INDEX[did]['produces']
    if not deps and not produces:
        return ''

    lines = ['', '---', '', '!!! info "本頁完成後"', '']
    if produces:
        lines.append(f'    **產出資料**：{"、".join(produces)}')
        lines.append('')
    if deps:
        lines.append('    **下列作業需要上述資料才能進行**：')
        lines.append('')
        for d in deps:
            lines.append(f'    - [{_INDEX[d]["title"]}]({_rel_link(src_uri, d)})')
    return '\n'.join(lines) + '\n'


def _dep_graph() -> str:
    """全站流程依賴圖。節點=頁面，邊上標的是流轉的資料名。"""
    linked = [d for d in _INDEX if _INDEX[d]['requires'] or _DEPENDENTS.get(d)]
    if not linked:
        # 還沒有任何頁面宣告 requires/produces，輸出空的 mermaid 會讓
        # 前端報 parse error，改成一句說明。
        return ('*（目前尚無文件宣告 `requires` / `produces` 關係，'
                '待內容補齊後此處會自動出現流程關係圖。）*')
    nid = {did: f'N{i}' for i, did in enumerate(sorted(_INDEX))}
    lines = ['```mermaid', 'flowchart TD']
    for did, info in sorted(_INDEX.items()):
        if not info['requires'] and not _DEPENDENTS.get(did):
            continue  # 孤立頁不入圖，避免雜訊
        lines.append(f'    {nid[did]}["{info["title"]}"]')
    for did, info in sorted(_INDEX.items()):
        for r in info['requires']:
            if r not in nid:
                continue
            label = '、'.join(_INDEX[r]['produces'])
            edge = f'-- {label} -->' if label else '-->'
            lines.append(f'    {nid[r]} {edge} {nid[did]}')
    lines.append('```')
    return '\n'.join(lines)


def on_page_markdown(markdown, page, config, files):
    did = _doc_id(page.file.src_uri)
    if did not in _INDEX:
        return markdown

    if '<!-- DEP_GRAPH -->' in markdown:
        markdown = markdown.replace('<!-- DEP_GRAPH -->', _dep_graph())

    src_uri = page.file.src_uri
    prereq = _prereq_block(did, src_uri)
    followup = _followup_block(did, src_uri)

    if prereq:
        # 插在 H1 之後，不要蓋掉頁面標題
        m = _H1_RE.search(markdown)
        if m:
            cut = m.end()
            markdown = markdown[:cut] + '\n\n' + prereq + markdown[cut:]
        else:
            markdown = prereq + markdown

    return markdown + followup


def on_post_build(config):
    """輸出 doc_map.json，供 scripts/docs_impact.py 做版控影響分析。"""
    out = Path(config['site_dir']) / 'doc_map.json'
    out.write_text(
        json.dumps(_INDEX, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
