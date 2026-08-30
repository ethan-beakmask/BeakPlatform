"""
BeakMask Organization Management Web Routes
企業管理網頁路由

僅限系統管理員存取
整合企業列表、合約管理、集團管理
"""
import json
from datetime import datetime, date
from flask import Blueprint, render_template, abort, jsonify, request, flash, redirect, url_for
from flask_babel import gettext as _
from flask_login import current_user
from sqlalchemy import or_

from sqlalchemy import func
from ..security.decorators import system_admin_required
from ..security.resource_gateway import ResourceGateway
from ..models.organization import DEFAULT_ORG_USER_LIMIT, Organization
from ..models.contract import Contract
from ..models.conglomerate import Conglomerate
from ..services.organization_service import OrganizationService
from ..services.conglomerate_service import ConglomerateService
from ..services.code_generator import get_code_generator
from ..services.lookup_service import LookupService
from ..services.org_data_purge_service import (
    HARD_DELETE_DISPLAY_NAMES,
    ORG_DISPLAY_NAME,
    build_hard_delete_sequence,
    hard_delete_stmts,
    physical_error_entry,
    run_delete_with_retries,
)
from ..services.org_physical_cleanup_service import (
    collect_org_file_records,
    delete_org_files,
    list_org_database_manual_items,
    list_org_existing_directories,
    remove_org_directories,
)
from .. import db

organizations_bp = Blueprint('organizations', __name__)

# 每頁筆數
PER_PAGE = 50


@organizations_bp.route('/')
@system_admin_required
def list_orgs():
    """
    企業管理頁面 - 整合企業列表、合約管理、集團管理
    """
    from dateutil.relativedelta import relativedelta

    # 取得查詢參數
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    conglomerate_filter = request.args.get('conglomerate', '').strip()
    selected_org_code = request.args.get('org', '').strip()

    # 建立查詢
    query = Organization.query.filter(Organization.is_deleted == False)

    # 模糊搜尋（名稱、網域、代碼）
    if search:
        search_pattern = f'%{search}%'
        query = query.filter(or_(
            Organization.name.ilike(search_pattern),
            Organization.domain_name.ilike(search_pattern),
            Organization.code.ilike(search_pattern)
        ))

    # 集團篩選
    if conglomerate_filter:
        if conglomerate_filter == 'none':
            query = query.filter(Organization.conglomerate_secure_code == None)
        else:
            query = query.filter(Organization.conglomerate_secure_code == conglomerate_filter)

    # 計算總數和分頁
    total = query.count()
    pages = (total + PER_PAGE - 1) // PER_PAGE
    page = max(1, min(page, pages)) if pages > 0 else 1

    # 取得分頁資料（啟用在前、停用在後）
    organizations = query.order_by(
        Organization.is_active.desc(),
        Organization.conglomerate_secure_code.asc().nullslast(),
        Organization.name
    ).offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()

    # 取得所有集團（用於篩選下拉）
    conglomerates = Conglomerate.query.filter(
        Conglomerate.is_deleted == False,
        Conglomerate.is_active == True
    ).order_by(Conglomerate.name).all()

    # 建立集團名稱映射
    conglomerate_map = {c.secure_code: c for c in conglomerates}

    # 計算每個企業的合約數量
    from sqlalchemy import func
    today = date.today()

    # 有效合約數量（狀態為 ACTIVE 且在有效期間內）
    active_contract_counts = db.session.query(
        Contract.org_secure_code,
        func.count(Contract.id).label('count')
    ).filter(
        Contract.is_deleted == False,
        Contract.status == 'ACTIVE',
        Contract.start_date <= today,
        Contract.end_date >= today
    ).group_by(Contract.org_secure_code).all()

    org_active_counts = {row[0]: row[1] for row in active_contract_counts}

    # 總合約數量（所有未刪除的合約）
    total_contract_counts = db.session.query(
        Contract.org_secure_code,
        func.count(Contract.id).label('count')
    ).filter(
        Contract.is_deleted == False
    ).group_by(Contract.org_secure_code).all()

    org_total_counts = {row[0]: row[1] for row in total_contract_counts}

    # 處理選中的企業
    selected_org = None
    contracts = []
    contract_period = None

    if selected_org_code:
        selected_org = Organization.query.filter_by(
            secure_code=selected_org_code,
            is_deleted=False
        ).first()

        if selected_org:
            # 取得該企業的合約
            contracts = Contract.query.filter_by(
                org_secure_code=selected_org.secure_code,
                is_deleted=False
            ).order_by(Contract.start_date.desc()).all()

            # 計算合約期間（只計算非停用的合約）
            active_contracts = [c for c in contracts if c.status == 'ACTIVE']
            if active_contracts:
                start_dates = [c.start_date for c in active_contracts]
                end_dates = [c.end_date for c in active_contracts]
                earliest = min(start_dates)
                latest = max(end_dates)

                today = date.today()
                if latest >= today:
                    rd = relativedelta(latest, today)
                    remaining = _('%(y)s年%(m)s個月', y=rd.years, m=rd.months) if rd.years > 0 else _('%(m)s個月%(d)s天', m=rd.months, d=rd.days)
                else:
                    rd = relativedelta(today, latest)
                    remaining = _('已過期 %(y)s年%(m)s個月', y=rd.years, m=rd.months) if rd.years > 0 else _('已過期 %(m)s個月%(d)s天', m=rd.months, d=rd.days)

                contract_period = {
                    'start': earliest,
                    'end': latest,
                    'remaining': remaining,
                    'is_expired': latest < today
                }

    # 計算分頁範圍（顯示最多 5 頁）
    page_range_start = max(1, page - 2)
    page_range_end = min(pages, page + 2)
    page_range = list(range(page_range_start, page_range_end + 1))

    # 序列化合約資料供前端 Alpine.js 使用
    contracts_json = json.dumps([c.to_dict() for c in contracts]) if contracts else '[]'

    return render_template(
        'pages/organizations/list.html',
        organizations=organizations,
        conglomerates=conglomerates,
        conglomerate_map=conglomerate_map,
        org_active_counts=org_active_counts,
        org_total_counts=org_total_counts,
        selected_org=selected_org,
        contracts=contracts,
        contracts_json=contracts_json,
        contract_period=contract_period,
        pagination={
            'page': page,
            'pages': pages,
            'total': total,
            'per_page': PER_PAGE,
            'page_range': page_range
        },
        search=search,
        conglomerate_filter=conglomerate_filter,
        available_modules=LookupService.get_items('INSTALLED_MODULES')
    )


@organizations_bp.route('/<secure_code>')
@system_admin_required
def view_org(secure_code: str):
    """企業詳情 - 已併入 list.html 右側面板，重導至列表頁"""
    return redirect(url_for('organizations.list_orgs', org=secure_code))


@organizations_bp.route('/create', methods=['GET', 'POST'])
@system_admin_required
def create_org():
    """建立企業頁面"""
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        name = request.form.get('name', '').strip()
        display_name = request.form.get('display_name', '').strip() or None
        domain_name = request.form.get('domain_name', '').strip().lower()
        description = request.form.get('description', '').strip() or None
        user_limit_str = request.form.get('user_limit', '').strip()
        admin_username = request.form.get('admin_username', 'admin').strip() or 'admin'
        admin_password = request.form.get('admin_password', '').strip()

        # code 空白時自動產生
        if not code and name:
            generator = get_code_generator()
            def _exists(c):
                return Organization.query.filter(
                    func.upper(Organization.code) == c.upper(),
                    Organization.is_deleted == False
                ).first() is not None
            try:
                code = generator.generate(name, exists_checker=_exists)
            except ValueError:
                flash(_('無法自動產生企業代碼，請手動輸入'), 'error')

        if not code or not name or not domain_name:
            flash(_('企業代碼、企業名稱、網域名稱為必填'), 'error')
        elif not domain_name.replace('-', '').replace('.', '').isalnum():
            flash(_('網域名稱只能包含字母、數字、連字號和點'), 'error')
        elif not admin_password:
            flash(_('管理員密碼為必填'), 'error')
        elif len(admin_password) < 12:
            flash(_('管理員密碼長度至少 12 碼'), 'error')
        elif user_limit_str and (not user_limit_str.isdigit() or int(user_limit_str) < 1):
            flash(_('帳號上限必須為正整數'), 'error')
        else:
            try:
                from datetime import timedelta
                org, admin_user = OrganizationService.create_organization(
                    code=code,
                    name=name,
                    display_name=display_name,
                    domain_name=domain_name,
                    description=description,
                    user_limit=int(user_limit_str) if user_limit_str else DEFAULT_ORG_USER_LIMIT,
                    admin_username=admin_username,
                    admin_password=admin_password,
                    created_by=current_user.email
                )

                # 自動建立 10 天試用合約（預設啟用流程模組）
                today = date.today()
                OrganizationService.create_contract(
                    org_secure_code=org.secure_code,
                    start_date=today,
                    end_date=today + timedelta(days=10),
                    name=f'{name} 試用合約',
                    modules_config=json.dumps(['form_workflow']),
                    created_by=current_user.secure_code
                )

                db.session.commit()

                admin_info = f'{admin_username}@{domain_name}'
                flash(_('已建立企業 %(name)s（含 10 天試用合約），管理員帳號: %(admin_info)s',
                        name=name, admin_info=admin_info), 'success')
                return redirect(url_for('organizations.list_orgs', org=org.secure_code))
            except ValueError as e:
                db.session.rollback()
                flash(str(e), 'error')
            except Exception as e:
                db.session.rollback()
                flash(_('建立失敗: %(error)s', error=str(e)), 'error')

    return render_template(
        'pages/organizations/create.html',
        default_user_limit=DEFAULT_ORG_USER_LIMIT
    )


@organizations_bp.route('/<secure_code>/edit', methods=['GET', 'POST'])
@system_admin_required
def edit_org(secure_code: str):
    """編輯企業頁面"""
    org = ResourceGateway.get_by(
        Organization,
        secure_code=secure_code,
        is_deleted=False,
        check_permission=False
    )
    if not org:
        abort(404)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        display_name = request.form.get('display_name', '').strip() or None
        description = request.form.get('description', '').strip() or None
        is_active = request.form.get('is_active') == 'true'
        customer_type = request.form.get('customer_type', '').strip()
        user_limit_str = request.form.get('user_limit', '').strip()
        contact_person = request.form.get('contact_person', '').strip() or None
        contact_email = request.form.get('contact_email', '').strip() or None
        contact_phone = request.form.get('contact_phone', '').strip() or None
        address = request.form.get('address', '').strip() or None

        if not name:
            flash(_('企業名稱為必填'), 'error')
        else:
            try:
                org.name = name
                org.display_name = display_name
                org.description = description
                org.is_active = is_active
                if customer_type in ('TRIAL', 'FORMAL', 'BLACKLIST'):
                    org.customer_type = customer_type
                if user_limit_str:
                    user_limit = int(user_limit_str)
                    if user_limit >= 1:
                        org.user_limit = user_limit
                org.contact_person = contact_person
                org.contact_email = contact_email
                org.contact_phone = contact_phone
                org.address = address
                db.session.commit()
                flash(_('已更新企業資料'), 'success')
                return redirect(url_for('organizations.list_orgs'))
            except ValueError:
                db.session.rollback()
                flash(_('帳號上限必須為正整數'), 'error')
            except Exception as e:
                db.session.rollback()
                flash(_('更新失敗: %(error)s', error=str(e)), 'error')

    # 查詢未到期的有效合約（狀態 ACTIVE 且結束日期 >= 今天）
    today = date.today()
    active_contracts = Contract.query.filter(
        Contract.org_secure_code == org.secure_code,
        Contract.is_deleted == False,
        Contract.status == 'ACTIVE',
        Contract.end_date >= today
    ).order_by(Contract.end_date.desc()).all()

    # 目前啟用帳號數
    active_user_count = org.get_active_user_count()

    return render_template(
        'pages/organizations/edit.html',
        organization=org,
        active_contracts=active_contracts,
        active_user_count=active_user_count
    )


@organizations_bp.route('/<secure_code>/delete', methods=['POST'])
@system_admin_required
def delete_org(secure_code: str):
    """刪除企業"""
    org = ResourceGateway.get_by(
        Organization,
        secure_code=secure_code,
        is_deleted=False,
        check_permission=False
    )
    if not org:
        abort(404)

    # 系統企業不可刪除
    if org.is_system_org:
        flash(_('系統企業不可刪除'), 'error')
        return redirect(url_for('organizations.edit_org', secure_code=secure_code))

    try:
        now = datetime.utcnow()

        # 軟刪除相關合約
        contracts = Contract.query.filter_by(
            org_secure_code=org.secure_code,
            is_deleted=False
        ).all()
        for contract in contracts:
            contract.is_deleted = True
            contract.deleted_at = now

        # 從集團移除
        if org.conglomerate_secure_code:
            ConglomerateService.remove_organizations(
                org.conglomerate_secure_code,
                [org.secure_code],
                current_user.email
            )

        # 軟刪除企業
        org.is_deleted = True
        org.deleted_at = now
        org.is_active = False
        db.session.commit()

        contract_count = len(contracts)
        if contract_count > 0:
            msg = _('已刪除企業 %(name)s（含 %(count)s 份合約）',
                    name=org.name, count=contract_count)
        else:
            msg = _('已刪除企業 %(name)s', name=org.name)
        flash(msg, 'success')
        return redirect(url_for('organizations.list_orgs'))
    except Exception as e:
        db.session.rollback()
        flash(_('刪除失敗: %(error)s', error=str(e)), 'error')
        return redirect(url_for('organizations.edit_org', secure_code=secure_code))


# ---------------------------------------------------------------------------
# 硬刪除已軟刪除的企業（PF-170：由 /hostconfig/data-maintenance 搬來）
#
# 這是唯一以「還存在的企業」為對象的清理動作，所以放在企業管理底下。
# 對象是「已不存在企業」的殘留（孤兒資料、無主檔案、孤兒目錄）屬主機層面，
# 留在 /hostconfig/data-maintenance「主機資料清理」，兩者不要互相搬。
#
# 刪除核心與孤兒清理共用 services/org_data_purge_service.py，禁止各自複製。
# ---------------------------------------------------------------------------

@organizations_bp.route('/hard-delete/preview', methods=['GET'])
@system_admin_required
def hard_delete_preview():
    """
    預覽硬刪除將刪除的資料

    Returns:
        - deleted_orgs: 已軟刪除的企業列表
        - table_counts: 各表預計刪除的筆數
    """
    try:
        # 繞過 RLS，確保能看到所有企業隔離的資料
        db.session.execute(db.text("SET LOCAL app.is_system_admin = 'true'"))

        # 取得已軟刪除的企業
        result = db.session.execute(db.text(
            "SELECT secure_code, code, name, domain_name "
            "FROM organizations WHERE is_deleted = true"
        ))
        deleted_orgs = [
            {'secure_code': row[0], 'code': row[1], 'name': row[2], 'domain_name': row[3]}
            for row in result
        ]

        if not deleted_orgs:
            return jsonify({
                'success': True,
                'deleted_orgs': [],
                'table_counts': [],
                'physical': {
                    'file_count': 0,
                    'directories': [],
                    'manual_required': [],
                },
                'message': _('沒有已軟刪除的企業')
            })

        # 取得各表預計刪除的筆數
        org_codes = [org['secure_code'] for org in deleted_orgs]
        ordered_tables, all_tables = build_hard_delete_sequence()

        table_counts = []
        for table_name in ordered_tables:
            try:
                with db.session.begin_nested():
                    count_stmt, _unused = hard_delete_stmts(table_name, all_tables)
                    count = db.session.execute(count_stmt, {'orgs': org_codes}).scalar()
                    if count > 0:
                        table_counts.append({
                            'table': table_name,
                            'display_name': HARD_DELETE_DISPLAY_NAMES.get(table_name, table_name),
                            'count': count
                        })
            except Exception:
                # savepoint 自動 rollback，表可能不存在，跳過
                pass

        table_counts.append({
            'table': 'organizations',
            'display_name': HARD_DELETE_DISPLAY_NAMES.get('organizations', 'organizations'),
            'count': len(deleted_orgs),
        })
        physical = {
            'file_count': len(collect_org_file_records(org_codes)),
            'directories': list_org_existing_directories(org_codes),
            'manual_required': list_org_database_manual_items(org_codes),
        }

        return jsonify({
            'success': True,
            'deleted_orgs': deleted_orgs,
            'table_counts': table_counts,
            'physical': physical,
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@organizations_bp.route('/hard-delete/execute', methods=['POST'])
@system_admin_required
def hard_delete_execute():
    """
    執行硬刪除

    刪除所有已軟刪除企業的相關資料（永久刪除，無法復原）
    """
    try:
        # 繞過 RLS，確保能刪除所有企業隔離的資料
        db.session.execute(db.text("SET LOCAL app.is_system_admin = 'true'"))

        # 取得已軟刪除的企業
        result = db.session.execute(db.text(
            "SELECT secure_code FROM organizations WHERE is_deleted = true"
        ))
        org_codes = [row[0] for row in result]

        if not org_codes:
            return jsonify({
                'success': True,
                'message': _('沒有需要刪除的資料'),
                'deleted_counts': {},
                'has_errors': False,
                'errors': [],
                'physical': {
                    'files_deleted': 0,
                    'files_missing': 0,
                    'dirs_removed': [],
                    'manual_required': [],
                },
            })

        deleted_counts = {}
        errors = []
        manual_items = list_org_database_manual_items(org_codes)
        file_result = delete_org_files(org_codes)
        ordered_tables, all_tables = build_hard_delete_sequence()

        # 按順序刪除各表（用 SAVEPOINT 隔離個別表的錯誤）
        table_counts, table_errors = run_delete_with_retries(
            ordered_tables,
            lambda table_name: (
                hard_delete_stmts(table_name, all_tables)[1],
                {'orgs': org_codes},
            ),
        )
        for table_name, count in table_counts.items():
            display_name = HARD_DELETE_DISPLAY_NAMES.get(table_name, table_name)
            deleted_counts[display_name] = deleted_counts.get(display_name, 0) + count
        errors.extend(table_errors)

        try:
            with db.session.begin_nested():
                result = db.session.execute(db.text(
                    "DELETE FROM organizations WHERE is_deleted = true"
                ))
                if result.rowcount > 0:
                    deleted_counts[ORG_DISPLAY_NAME] = result.rowcount
        except Exception as e:
            errors.append({
                'table': 'organizations',
                'display_name': ORG_DISPLAY_NAME,
                'error': str(e),
            })

        db.session.commit()
        dir_result = remove_org_directories(org_codes)
        errors.extend(physical_error_entry(error) for error in file_result['errors'])
        errors.extend(physical_error_entry(error) for error in dir_result['errors'])
        for error in errors:
            deleted_counts[f"{error['display_name']} (錯誤)"] = error['error']

        return jsonify({
            'success': True,
            'message': (
                _('刪除過程有 %(n)s 項失敗，企業可能未完全刪除', n=len(errors))
                if errors else _('已刪除 %(count)s 個企業及其相關資料', count=len(org_codes))
            ),
            'deleted_counts': deleted_counts,
            'has_errors': bool(errors),
            'errors': errors,
            'physical': {
                'files_deleted': file_result['files_deleted'],
                'files_missing': file_result['files_missing'],
                'dirs_removed': dir_result['dirs_removed'],
                'manual_required': manual_items,
            },
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
