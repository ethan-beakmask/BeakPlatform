"""
BeakPlatform Help Pages
平台說明文件 + 頁內 [?] 按鈕對應的 per-page 說明
"""
from flask import Blueprint, abort, jsonify, render_template, request
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import login_required
from ..services import doc_catalog_service, help_service

platform_help_bp = Blueprint('platform_help', __name__)


CONCEPTS_NAV_ID = '__concepts__'
CONCEPTS_USER_TYPES = ('SYSTEM_ADMIN', 'ORG_ADMIN')


def _can_read_concepts() -> bool:
    """平台概念說明限管理員閱讀（左側目錄與路由共用同一個判定）"""
    return str(current_user.user_type) in CONCEPTS_USER_TYPES


@platform_help_bp.route('/')
@login_required
def index():
    """依登入者身分顯示可閱讀的手冊目錄"""
    chapters = doc_catalog_service.list_manual(current_user)
    return render_template(
        'pages/platform_help/index.html',
        chapters=chapters,
        current_doc_id=None,
        current_chapter_id=None,
        show_concepts=_can_read_concepts(),
        open_map=_manual_open_map(chapters, open_all=True),
    )


@platform_help_bp.route('/manual/<path:doc_id>')
@login_required
def manual_doc(doc_id: str):
    """顯示單頁使用者手冊"""
    doc = doc_catalog_service.get_manual_doc(doc_id, current_user)
    if doc is None:
        abort(404)
    chapters = doc_catalog_service.list_manual(current_user)
    current_chapter_id = _chapter_id_from_doc_id(doc['doc_id'])
    return render_template(
        'pages/platform_help/manual_doc.html',
        doc=doc,
        chapters=chapters,
        current_doc_id=doc['doc_id'],
        current_chapter_id=current_chapter_id,
        show_concepts=_can_read_concepts(),
        open_map=_manual_open_map(chapters, current_doc_id=doc['doc_id']),
    )


def _chapter_id_from_doc_id(doc_id: str) -> str | None:
    parts = doc_id.split('/')
    if len(parts) >= 2 and parts[0] == 'manual':
        return parts[1]
    return None


def _section_open_key(chapter_id: str, section_id: str) -> str:
    return f"section:{chapter_id}/{section_id}"


def _section_id_from_doc_id(doc_id: str) -> str | None:
    parts = doc_id.split('/')
    if len(parts) >= 4 and parts[0] == 'manual':
        return parts[2]
    return None


def _manual_open_map(
    chapters: list[dict],
    current_doc_id: str | None = None,
    open_all: bool = False,
) -> dict[str, bool]:
    current_chapter_id = _chapter_id_from_doc_id(current_doc_id or '')
    current_section_id = _section_id_from_doc_id(current_doc_id or '')
    open_map = {}

    for chapter in chapters:
        chapter_id = chapter['chapter_id']
        open_map[chapter_id] = open_all or chapter_id == current_chapter_id
        for entry in chapter.get('entries', []):
            if entry.get('kind') != 'section':
                continue
            section_id = entry['section_id']
            open_map[_section_open_key(chapter_id, section_id)] = (
                open_all
                or (
                    chapter_id == current_chapter_id
                    and section_id == current_section_id
                )
            )

    return open_map


@platform_help_bp.route('/concepts')
@login_required
def concepts():
    """顯示平台概念說明（版面與手冊一致，左側掛同一份目錄）"""
    if not _can_read_concepts():
        abort(404)
    chapters = doc_catalog_service.list_manual(current_user)
    return render_template(
        'pages/platform_help/org_admin.html',
        chapters=chapters,
        current_doc_id=CONCEPTS_NAV_ID,
        current_chapter_id=None,
        show_concepts=True,
        open_map=_manual_open_map(chapters),
    )


@platform_help_bp.route('/page/<menu_code>')
@login_required
def page_doc(menu_code: str):
    """整頁顯示某個 menu_code 對應的 help 文件"""
    doc = help_service.load_doc(menu_code)
    user_type = str(current_user.user_type)
    rendered = help_service.render_for_audience(doc, user_type) if doc else None
    return render_template(
        'pages/platform_help/page_doc.html',
        menu_code=menu_code,
        doc=rendered,
        user_type=user_type,
    )


@platform_help_bp.route('/api/page')
@login_required
def api_page_doc():
    """
    Modal 用 API：依 endpoint / path 反查 menu_code 並回傳 HTML
    Query params:
      - endpoint: Flask endpoint 名（如 'users.list_users'）
      - path: URL path（如 '/access/'，已去掉 APP_PREFIX）
    """
    endpoint = request.args.get('endpoint') or None
    path = request.args.get('path') or None

    menu_code = help_service.menu_code_for_endpoint(endpoint, path)
    if not menu_code:
        return jsonify({
            'found': False,
            'menu_code': None,
            'message': _('此頁面尚未提供說明文件'),
        })

    doc = help_service.load_doc(menu_code)
    if not doc:
        return jsonify({
            'found': False,
            'menu_code': menu_code,
            'message': _('此頁面尚未提供說明文件'),
        })

    user_type = str(current_user.user_type)
    rendered = help_service.render_for_audience(doc, user_type)
    return jsonify({
        'found': True,
        'menu_code': menu_code,
        'title': rendered['title'],
        'sections': rendered['sections'],
    })
