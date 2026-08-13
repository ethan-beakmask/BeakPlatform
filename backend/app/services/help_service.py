"""
Help 文件載入服務

文件位置: docs/help/<menu_code>.md
格式: YAML frontmatter + Markdown body

frontmatter 範例:
---
menu_code: users
title: 用戶管理
audiences:
  - SYSTEM_ADMIN
  - ORG_ADMIN
sections:
  - audience: ORG_ADMIN
    body: |
      ## 用戶管理（企業管理員視角）
      ...
  - audience: SYSTEM_ADMIN
    body: |
      ## 用戶管理（系統管理員視角）
      ...
---

設計：
- 啟動時掃描一次，dev 模式下檔案 mtime 變更時自動 reload
- 依 user_type 過濾 sections，沒有對應 audience 時 fallback 到第一段
- 找不到 menu_code 對應檔 → 回 None，由 caller 處理 fallback
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import markdown
import yaml
from flask import current_app

logger = logging.getLogger(__name__)


_FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n(.*)$', re.DOTALL)
_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def _help_dir() -> str:
    """docs/help/ 絕對路徑"""
    base = current_app.config.get('HELP_DOC_DIR')
    if base:
        return base
    # backend/app -> ../../dev-notes/help
    return os.path.normpath(os.path.join(
        current_app.root_path, '..', '..', 'docs', 'help'
    ))


def _parse_file(path: str) -> Optional[Dict[str, Any]]:
    """讀檔解析 frontmatter + body"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read()
    except OSError:
        return None

    match = _FRONTMATTER_RE.match(raw)
    if not match:
        logger.warning(f"help doc missing frontmatter: {path}")
        return None

    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        logger.warning(f"help doc YAML error {path}: {exc}")
        return None

    fallback_body = match.group(2).strip()
    if not isinstance(meta, dict):
        return None

    if 'sections' not in meta and fallback_body:
        meta['sections'] = [{'audience': '*', 'body': fallback_body}]

    return meta


def load_doc(menu_code: str) -> Optional[Dict[str, Any]]:
    """載入單一 help doc，含 mtime cache"""
    if not menu_code:
        return None
    safe = re.sub(r'[^a-zA-Z0-9_.-]', '', menu_code)
    if not safe:
        return None
    path = os.path.join(_help_dir(), f'{safe}.md')
    if not os.path.isfile(path):
        return None

    mtime = os.path.getmtime(path)
    cached = _CACHE.get(safe)
    if cached and cached[0] == mtime:
        return cached[1]

    parsed = _parse_file(path)
    if parsed is not None:
        _CACHE[safe] = (mtime, parsed)
    return parsed


def render_for_audience(doc: Dict[str, Any], user_type: str) -> Dict[str, Any]:
    """
    依 user_type 過濾出該角色看得到的內容區段

    Returns:
        {
            'title': str,
            'sections': [{'audience': ..., 'html': ...}, ...],
            'audiences': [...],   # 此頁所有 audiences (供切換)
        }
    """
    sections = doc.get('sections') or []
    matched: List[Dict[str, Any]] = []
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        aud = sec.get('audience') or '*'
        if aud == '*' or aud == user_type:
            body = sec.get('body') or ''
            matched.append({
                'audience': aud,
                'html': markdown.markdown(body, extensions=['extra', 'sane_lists']),
            })

    if not matched and sections:
        # fallback: 顯示第一段 + 提示
        first = sections[0]
        if isinstance(first, dict):
            body = first.get('body') or ''
            matched.append({
                'audience': first.get('audience') or '*',
                'html': markdown.markdown(body, extensions=['extra', 'sane_lists']),
            })

    return {
        'title': doc.get('title') or '',
        'sections': matched,
        'audiences': doc.get('audiences') or [],
    }


def menu_code_for_endpoint(endpoint: Optional[str], path: Optional[str] = None) -> Optional[str]:
    """
    依 Flask endpoint / URL path 反查 menu_items.code

    優先順序：
    1. link_type='route' 且 link_target == endpoint
    2. link_type='url' 且 link_target == path（去掉 trailing slash 後比對）
    """
    from ..models import MenuItem

    if endpoint:
        item = MenuItem.query.filter(
            MenuItem.link_type == 'route',
            MenuItem.link_target == endpoint,
            MenuItem.is_deleted == False,  # noqa: E712
            MenuItem.is_active == True,    # noqa: E712
        ).first()
        if item:
            return item.code

    if path:
        normalized = path.rstrip('/')
        candidates = MenuItem.query.filter(
            MenuItem.link_type.in_(['url', 'route']),
            MenuItem.link_target.isnot(None),
            MenuItem.link_target.like('/%'),
            MenuItem.is_deleted == False,  # noqa: E712
            MenuItem.is_active == True,    # noqa: E712
        ).all()
        best = None
        best_len = -1
        for item in candidates:
            target = (item.link_target or '').rstrip('/')
            if normalized == target and len(target) > best_len:
                best, best_len = item, len(target)
        if best:
            return best.code

    return None


def list_all_docs() -> List[Dict[str, Any]]:
    """列出所有 help doc 的 metadata（給索引頁用）"""
    base = _help_dir()
    if not os.path.isdir(base):
        return []
    out = []
    for fn in sorted(os.listdir(base)):
        if not fn.endswith('.md'):
            continue
        code = fn[:-3]
        doc = load_doc(code)
        if not doc:
            continue
        out.append({
            'menu_code': code,
            'title': doc.get('title') or code,
            'audiences': doc.get('audiences') or [],
        })
    return out
