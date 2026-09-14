"""
使用者手冊目錄服務

掃描 docs/manual 的 Markdown frontmatter，依登入者目前可見的選單結果與角色
產生站內說明目錄。文件可見性直接複用 MenuService.get_user_menu_tree() 的結果，
不在此服務重新計算選單權限。
"""
from __future__ import annotations

import logging
import os
import posixpath
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml
import markdown
from flask import current_app, g, has_request_context, url_for
from flask_babel import gettext as _

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n(.*)$', re.DOTALL)
_DOC_ID_RE = re.compile(r'^manual/[0-9a-z_]+/[0-9a-z_]+(/[0-9a-z_]+)?$')
_MD_LINK_RE = re.compile(r'(\]\()([^)\s]+\.md(?:#[^)]+)?)(\))')
_LOCALE_SUFFIXES = ('en', 'ja', 'zh-cn')
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


def _variant_stem(stem: str) -> Tuple[str, Optional[str]]:
    if '.' not in stem:
        return stem, None
    base_stem, suffix = stem.rsplit('.', 1)
    suffix = suffix.lower()
    if suffix in _LOCALE_SUFFIXES and base_stem:
        return base_stem, suffix
    return stem, None


def _split_manual_files(directory: str) -> Tuple[
    List[Tuple[str, str, str]],
    Dict[str, Dict[str, Tuple[str, str]]],
]:
    main_files: List[Tuple[str, str, str]] = []
    variants: Dict[str, Dict[str, Tuple[str, str]]] = {}

    for filename in sorted(os.listdir(directory)):
        path = os.path.join(directory, filename)
        if not filename.endswith('.md') or not os.path.isfile(path):
            continue

        stem = filename[:-3]
        base_stem, lang = _variant_stem(stem)
        if lang:
            variants.setdefault(base_stem, {})[lang] = (filename, path)
        else:
            main_files.append((filename, stem, path))

    main_stems = {stem for _, stem, _ in main_files}
    valid_variants: Dict[str, Dict[str, Tuple[str, str]]] = {}
    for stem, stem_variants in variants.items():
        if stem not in main_stems:
            for filename, path in stem_variants.values():
                logger.warning(
                    "manual doc locale variant ignored without base file: %s",
                    path,
                )
            continue
        valid_variants[stem] = stem_variants

    return main_files, valid_variants


def _load_variants(
    stem: str,
    variants_by_stem: Dict[str, Dict[str, Tuple[str, str]]],
) -> Dict[str, Dict[str, str]]:
    variants: Dict[str, Dict[str, str]] = {}
    for lang, (_, path) in sorted(variants_by_stem.get(stem, {}).items()):
        parsed = _parse_file(path)
        if not parsed:
            logger.warning("manual doc locale variant ignored: %s", path)
            continue
        meta = parsed['meta']
        variants[lang] = {
            'title': str(meta.get('title') or ''),
            'body': parsed['body'],
        }
    return variants


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
                'index_item': None,
                'entries': [],
            }

            for filename in sorted(os.listdir(chapter_dir)):
                path = os.path.join(chapter_dir, filename)
                if os.path.isdir(path):
                    section = _load_section(chapter_id, filename, path, docs)
                    if section:
                        chapter['entries'].append(section)
                    continue

            main_files, variants_by_stem = _split_manual_files(chapter_dir)
            for filename, stem, path in main_files:
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
                    'section_id': None,
                    'variants': _load_variants(stem, variants_by_stem),
                }
                docs[doc_id] = item

                if filename == 'index.md' or meta.get('chapter_index') is True:
                    chapter['title'] = meta.get('title') or chapter_id
                    chapter['chapter_order'] = meta.get('chapter_order', 999999)
                    chapter['index_doc_id'] = doc_id
                    chapter['index_item'] = item
                else:
                    chapter['entries'].append({
                        'kind': 'doc',
                        'order': item['order'],
                        'sort_key': item['filename'],
                        **item,
                    })

            chapters[chapter_id] = chapter

    catalog = {
        'docs': docs,
        'chapters': chapters,
    }
    _CACHE['signature'] = sig
    _CACHE['catalog'] = catalog
    return catalog


def _load_section(
    chapter_id: str,
    section_id: str,
    section_dir: str,
    docs: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    section = {
        'kind': 'section',
        'chapter_id': chapter_id,
        'section_id': section_id,
        'title': section_id,
        'order': 999999,
        'sort_key': section_id,
        'index_doc_id': None,
        'index_item': None,
        'docs': [],
    }

    main_files, variants_by_stem = _split_manual_files(section_dir)
    for filename, stem, path in main_files:
        parsed = _parse_file(path)
        if not parsed:
            continue

        doc_id = f'manual/{chapter_id}/{section_id}/{stem}'
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
            'section_id': section_id,
            'variants': _load_variants(stem, variants_by_stem),
        }
        docs[doc_id] = item

        if filename == 'index.md' or meta.get('section_index') is True:
            section['title'] = meta.get('title') or section_id
            section['order'] = meta.get('order', 999999)
            section['index_doc_id'] = doc_id
            section['index_item'] = item
        else:
            section['docs'].append(item)

    if not section['index_doc_id'] and not section['docs']:
        return None
    return section


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


def _current_locale() -> Optional[str]:
    if not has_request_context():
        return None
    locale = getattr(g, 'locale', None)
    if locale is None:
        return None
    locale = str(locale).lower()
    if locale in _LOCALE_SUFFIXES:
        return locale
    return None


def resolve_localized(item: Dict[str, Any]) -> Tuple[str, str, bool]:
    title = item['title']
    body = item['body']
    locale = _current_locale()
    if not locale:
        return title, body, False

    variant = (item.get('variants') or {}).get(locale)
    # 變體只有 frontmatter、內文空白時視同沒有翻譯：回主檔並標記 fallback，
    # 否則使用者會看到一片空白而且沒有任何提示。
    if variant and (variant.get('body') or '').strip():
        return variant.get('title') or title, variant['body'], False

    return title, body, True


def doc_exists(doc_id) -> bool:
    if not isinstance(doc_id, str) or not doc_id:
        return False
    return doc_id in _load_catalog()['docs']


def _manual_doc_href(doc_id: str) -> str:
    try:
        return url_for('platform_help.manual_doc', doc_id=doc_id)
    except RuntimeError:
        return f"/help/manual/{doc_id}"


def _visible_doc_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    title = resolve_localized(item)[0]
    return {
        'kind': 'doc',
        'doc_id': item['doc_id'],
        'title': title,
    }


def _visible_section_summary(
    section: Dict[str, Any],
    user,
    menu_codes: Set[str],
) -> Optional[Dict[str, Any]]:
    index_item = section.get('index_item')
    if not index_item:
        # 節必須有 index.md（或 frontmatter section_index: true）當總覽，
        # 否則整節不會出現在目錄上。這裡出 warning 是為了避免靜默失效。
        logger.warning(
            "manual section without index doc, hidden from catalog: %s/%s",
            section.get('chapter_id'), section.get('section_id'),
        )
        return None
    if not is_doc_visible(index_item['meta'], user, menu_codes):
        return None

    visible_docs = [
        doc for doc in section.get('docs', [])
        if is_doc_visible(doc['meta'], user, menu_codes)
    ]
    if not visible_docs:
        return None

    visible_docs.sort(key=lambda d: (d['order'], d['filename']))
    title = resolve_localized(index_item)[0]
    return {
        'kind': 'section',
        'section_id': section['section_id'],
        'title': title,
        'index_doc_id': section['index_doc_id'],
        'docs': [_visible_doc_summary(doc) for doc in visible_docs],
    }


def list_manual(user) -> List[dict]:
    """列出登入者可閱讀的手冊章節樹。"""
    catalog = _load_catalog()
    menu_codes = visible_menu_codes(user)
    chapters = []

    for chapter in catalog['chapters'].values():
        visible_entries = []
        for entry in sorted(
            chapter.get('entries', []),
            key=lambda e: (e.get('order', 999999), e.get('sort_key', '')),
        ):
            if entry.get('kind') == 'section':
                section_summary = _visible_section_summary(entry, user, menu_codes)
                if section_summary:
                    visible_entries.append(section_summary)
                continue

            if is_doc_visible(entry['meta'], user, menu_codes):
                visible_entries.append(_visible_doc_summary(entry))

        if not visible_entries:
            continue

        chapter_title = chapter['title']
        if chapter.get('index_item'):
            chapter_title = resolve_localized(chapter['index_item'])[0]

        chapters.append({
            'chapter_id': chapter['chapter_id'],
            'title': chapter_title,
            'chapter_order': chapter['chapter_order'],
            'index_doc_id': chapter['index_doc_id'],
            'entries': visible_entries,
        })

    chapters.sort(key=lambda c: (c['chapter_order'], c['chapter_id']))
    return chapters


def _chapter_index_body(
    item: Dict[str, Any],
    chapter: Dict[str, Any],
    user,
    menu_codes: Set[str],
) -> Optional[str]:
    title = resolve_localized(item)[0]
    lines = [
        f"# {title}",
        '',
        _('本章包含以下主題：'),
        '',
    ]
    has_entries = False

    for entry in sorted(
        chapter.get('entries', []),
        key=lambda e: (e.get('order', 999999), e.get('sort_key', '')),
    ):
        if entry.get('kind') == 'section':
            section_summary = _visible_section_summary(entry, user, menu_codes)
            if not section_summary:
                continue
            lines.append(
                f"- [{section_summary['title']}]"
                f"({_manual_doc_href(section_summary['index_doc_id'])})"
            )
            has_entries = True
            continue

        if is_doc_visible(entry['meta'], user, menu_codes):
            entry_title = resolve_localized(entry)[0]
            lines.append(f"- [{entry_title}]({_manual_doc_href(entry['doc_id'])})")
            has_entries = True

    if not has_entries:
        return None
    return '\n'.join(lines)


def _section_index_body(
    item: Dict[str, Any],
    catalog: Dict[str, Any],
    user,
    menu_codes: Set[str],
) -> Optional[str]:
    chapter = catalog['chapters'].get(item['chapter_id']) or {}
    section = next(
        (
            entry for entry in chapter.get('entries', [])
            if entry.get('kind') == 'section'
            and entry.get('section_id') == item.get('section_id')
        ),
        None,
    )
    if not section:
        return None

    visible_docs = [
        doc for doc in section.get('docs', [])
        if is_doc_visible(doc['meta'], user, menu_codes)
    ]
    if not visible_docs:
        return None

    visible_docs.sort(key=lambda d: (d['order'], d['filename']))
    # 與章總覽不同：節總覽保留 md 原文（引言），動態清單接在後面。
    # 章總覽的 index.md 目前只有會過期的靜態清單，所以那邊仍是整段取代。
    body = resolve_localized(item)[1]
    lines = [
        body.strip(),
        '',
        _('本節包含以下主題：'),
        '',
    ]
    for doc in visible_docs:
        doc_title = resolve_localized(doc)[0]
        lines.append(f"- [{doc_title}]({_manual_doc_href(doc['doc_id'])})")
    return '\n'.join(lines).lstrip('\n')


def _rewrite_relative_md_links(
    body: str,
    doc_id: str,
    catalog: Dict[str, Any],
) -> str:
    doc_parts = str(doc_id).split('/')
    base_parts = doc_parts[1:-1]

    def replace(match: re.Match) -> str:
        target = match.group(2)
        if (
            target.startswith('#')
            or re.match(r'^[a-z][a-z0-9+.-]*:', target, re.IGNORECASE)
        ):
            return match.group(0)

        path_part, anchor = (target.split('#', 1) + [''])[:2] if '#' in target else (target, '')
        if not path_part.endswith('.md'):
            return match.group(0)

        stem_path = path_part[:-3]
        resolved = posixpath.normpath('/'.join([*base_parts, stem_path]))
        if resolved == '.':
            return match.group(0)
        if resolved.startswith('../') or resolved == '..':
            return match.group(0)

        target_doc_id = f"manual/{resolved}"
        if target_doc_id not in catalog['docs']:
            return match.group(0)

        href = _manual_doc_href(target_doc_id)
        if anchor:
            href = f"{href}#{anchor}"
        return f"{match.group(1)}{href}{match.group(3)}"

    return _MD_LINK_RE.sub(replace, body)


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
    title, body, locale_fallback = resolve_localized(item)
    if meta.get('chapter_index') is True:
        body = _chapter_index_body(item, chapter, user, menu_codes)
        if body is None:
            return None
    elif meta.get('section_index') is True:
        if not is_doc_visible(meta, user, menu_codes):
            return None
        body = _section_index_body(item, catalog, user, menu_codes)
        if body is None:
            return None
    elif not is_doc_visible(meta, user, menu_codes):
        return None

    body = _rewrite_relative_md_links(body, item['doc_id'], catalog)
    chapter_title = chapter.get('title') or ''
    if chapter.get('index_item'):
        chapter_title = resolve_localized(chapter['index_item'])[0]

    return {
        'doc_id': item['doc_id'],
        'title': title,
        'chapter_title': chapter_title,
        'locale_fallback': locale_fallback,
        'html': markdown.markdown(
            body,
            extensions=['extra', 'sane_lists', 'admonition'],
        ),
    }
