"""
使用者手冊目錄服務

掃描 docs/manual 的 Markdown frontmatter，依登入者目前可見的選單結果與角色
產生站內說明目錄。文件可見性直接複用 MenuService.get_user_menu_tree() 的結果，
不在此服務重新計算選單權限。
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml
import markdown
from flask import current_app, url_for
from flask_babel import gettext as _

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n(.*)$', re.DOTALL)
_DOC_ID_RE = re.compile(r'^manual/[0-9a-z_]+/[0-9a-z_]+$')
_ALL_USER_TYPES = {'SYSTEM_ADMIN', 'ORG_ADMIN', 'EMPLOYEE', 'EXTERNAL'}
_CACHE: Dict[str, Any] = {'signature': None, 'catalog': None}


def _manual_dir() -> str:
    """docs/manual/ 絕對路徑"""
    base = current_app.config.get('MANUAL_DOC_DIR')
    if base:
        return base
    return os.path.normpath(os.path.join(
        current_app.root_path, '..', '..', 'docs', 'manual'
    ))


def _as_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _parse_file(path: str) -> Optional[Dict[str, Any]]:
    """讀檔解析 frontmatter + body"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read()
    except OSError as exc:
        logger.warning(f"manual doc read error {path}: {exc}")
        return None

    match = _FRONTMATTER_RE.match(raw)
    if not match:
        logger.warning(f"manual doc missing frontmatter: {path}")
        return None

    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        logger.warning(f"manual doc YAML error {path}: {exc}")
        return None

    if not isinstance(meta, dict):
        logger.warning(f"manual doc frontmatter is not a mapping: {path}")
        return None

    return {
        'meta': meta,
        'body': match.group(2).strip(),
    }


def _signature(base: str) -> int:
    entries: List[Tuple[str, float]] = []
    if not os.path.isdir(base):
        return hash(tuple(entries))

    for root, _, files in os.walk(base):
        for filename in files:
            if not filename.endswith('.md'):
                continue
            path = os.path.join(root, filename)
            rel = os.path.relpath(path, base).replace(os.sep, '/')
            try:
                entries.append((rel, os.path.getmtime(path)))
            except OSError:
                continue
    return hash(tuple(sorted(entries)))


def _load_catalog() -> Dict[str, Any]:
    base = _manual_dir()
    sig = _signature(base)
    if _CACHE['signature'] == sig and _CACHE['catalog'] is not None:
        return _CACHE['catalog']

    docs: Dict[str, Dict[str, Any]] = {}
    chapters: Dict[str, Dict[str, Any]] = {}

    if os.path.isdir(base):
        for chapter_id in sorted(os.listdir(base)):
            chapter_dir = os.path.join(base, chapter_id)
            if not os.path.isdir(chapter_dir):
                continue

            chapter = {
                'chapter_id': chapter_id,
                'title': chapter_id,
                'chapter_order': 999999,
                'index_doc_id': f'manual/{chapter_id}/index',
                'docs': [],
            }

            for filename in sorted(os.listdir(chapter_dir)):
                if not filename.endswith('.md'):
                    continue
                stem = filename[:-3]
                path = os.path.join(chapter_dir, filename)
                parsed = _parse_file(path)
                if not parsed:
                    continue

                doc_id = f'manual/{chapter_id}/{stem}'
                meta = parsed['meta']
                item = {
                    'doc_id': doc_id,
                    'title': meta.get('title') or stem,
                    'order': meta.get('order', 999999),
                    'filename': stem,
                    'path': path,
                    'meta': meta,
                    'body': parsed['body'],
                    'chapter_id': chapter_id,
                }
                docs[doc_id] = item

                if filename == 'index.md' or meta.get('chapter_index') is True:
                    chapter['title'] = meta.get('title') or chapter_id
                    chapter['chapter_order'] = meta.get('chapter_order', 999999)
                    chapter['index_doc_id'] = doc_id
                else:
                    chapter['docs'].append(item)

            chapters[chapter_id] = chapter

    catalog = {
        'docs': docs,
        'chapters': chapters,
    }
    _CACHE['signature'] = sig
    _CACHE['catalog'] = catalog
    return catalog


def _flatten_menu_codes(nodes: Any, out: Set[str]) -> None:
    if isinstance(nodes, dict):
        iterable = [nodes]
    elif isinstance(nodes, list):
        iterable = nodes
    else:
        return
    for node in iterable:
        if not isinstance(node, dict):
            continue
        code = node.get('code')
        if code:
            out.add(str(code))
        _flatten_menu_codes(node.get('children') or [], out)


def visible_menu_codes(user) -> Set[str]:
    """取得登入者目前可見選單 code 集合。"""
    from .menu_service import MenuService

    try:
        tree = MenuService.get_user_menu_tree(user)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"manual doc menu visibility failed: {exc}")
        return set()

    codes: Set[str] = set()
    _flatten_menu_codes(tree, codes)
    return codes


def _user_role_codes(user) -> Set[str]:
    from ..models.associations import UserRoleAssignment
    from ..models.role import Role

    try:
        role_scs = UserRoleAssignment.get_active_role_secure_codes(user.secure_code)
        return {
            r.code for r in Role.query.filter(
                Role.secure_code.in_(role_scs),
                Role.is_deleted == False,  # noqa: E712
            ).all()
        } if role_scs else set()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"manual doc role visibility failed: {exc}")
        return set()


def is_doc_visible(meta, user, menu_codes) -> bool:
    """依 frontmatter 與登入者可見選單判定文件是否可讀。"""
    if meta.get('nav_menu'):
        return str(meta['nav_menu']) in menu_codes

    if meta.get('visible_user_types'):
        allowed_types = set(_as_list(meta.get('visible_user_types')))
    else:
        audience = str(meta.get('audience') or '')
        allowed_types = set(_ALL_USER_TYPES) if audience == 'ALL' else {audience}

    user_type = str(user.user_type)
    if user_type not in allowed_types:
        return False

    visible_roles = set(_as_list(meta.get('visible_roles')))
    if not visible_roles:
        return True

    if user_type in ('SYSTEM_ADMIN', 'ORG_ADMIN'):
        return True

    return bool(_user_role_codes(user) & visible_roles)


def list_manual(user) -> List[dict]:
    """列出登入者可閱讀的手冊章節樹。"""
    catalog = _load_catalog()
    menu_codes = visible_menu_codes(user)
    chapters = []

    for chapter in catalog['chapters'].values():
        visible_docs = []
        for item in chapter['docs']:
            if is_doc_visible(item['meta'], user, menu_codes):
                visible_docs.append({
                    'doc_id': item['doc_id'],
                    'title': item['title'],
                    '_order': item['order'],
                    '_filename': item['filename'],
                })

        if not visible_docs:
            continue

        visible_docs.sort(key=lambda d: (d['_order'], d['_filename']))
        for doc in visible_docs:
            doc.pop('_order', None)
            doc.pop('_filename', None)

        chapters.append({
            'chapter_id': chapter['chapter_id'],
            'title': chapter['title'],
            'chapter_order': chapter['chapter_order'],
            'index_doc_id': chapter['index_doc_id'],
            'docs': visible_docs,
        })

    chapters.sort(key=lambda c: (c['chapter_order'], c['chapter_id']))
    return chapters


def get_manual_doc(doc_id, user) -> Optional[dict]:
    """取得單頁手冊 HTML；不可見或不存在時回 None。"""
    if not doc_id or not _DOC_ID_RE.match(str(doc_id)):
        return None

    catalog = _load_catalog()
    item = catalog['docs'].get(str(doc_id))
    if not item or not os.path.isfile(item['path']):
        return None

    menu_codes = visible_menu_codes(user)
    chapter = catalog['chapters'].get(item['chapter_id']) or {}
    meta = item['meta']
    body = item['body']
    if meta.get('chapter_index') is True:
        visible_docs = [
            doc for doc in chapter.get('docs', [])
            if is_doc_visible(doc['meta'], user, menu_codes)
        ]
        if not visible_docs:
            return None
        visible_docs.sort(key=lambda d: (d['order'], d['filename']))
        lines = [
            f"# {item['title']}",
            '',
            _('本章包含以下主題：'),
            '',
        ]
        for doc in visible_docs:
            try:
                href = url_for('platform_help.manual_doc', doc_id=doc['doc_id'])
            except RuntimeError:
                href = f"/help/manual/{doc['doc_id']}"
            lines.append(f"- [{doc['title']}]({href})")
        body = '\n'.join(lines)
    elif not is_doc_visible(meta, user, menu_codes):
        return None

    return {
        'doc_id': item['doc_id'],
        'title': item['title'],
        'chapter_title': chapter.get('title') or '',
        'html': markdown.markdown(
            body,
            extensions=['extra', 'sane_lists', 'admonition'],
        ),
    }
