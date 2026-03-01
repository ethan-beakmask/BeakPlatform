"""
BeakMask Organization Management Web Routes
企業管理網頁路由

僅限系統管理員存取
整合企業列表、合約管理、集團管理
"""
import json
from datetime import datetime, date
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for
from flask_login import current_user
from sqlalchemy import or_

from sqlalchemy import func
from ..security.decorators import system_admin_required
from ..security.resource_gateway import ResourceGateway
from ..models.organization import Organization
from ..models.contract import Contract
from ..models.conglomerate import Conglomerate
from ..services.organization_service import OrganizationService
from ..services.conglomerate_service import ConglomerateService
from ..services.code_generator import get_code_generator
from ..services.lookup_service import LookupService
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
                    remaining = f"{rd.years}年{rd.months}個月" if rd.years > 0 else f"{rd.months}個月{rd.days}天"
                else:
                    rd = relativedelta(today, latest)
                    remaining = f"已過期 {rd.years}年{rd.months}個月" if rd.years > 0 else f"已過期 {rd.months}個月{rd.days}天"

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

    return render_template(
        'pages/organizations/list.html',
        organizations=organizations,
        conglomerates=conglomerates,
        conglomerate_map=conglomerate_map,
        org_active_counts=org_active_counts,
        org_total_counts=org_total_counts,
        selected_org=selected_org,
        contracts=contracts,
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
    """查看企業詳情"""
    org = ResourceGateway.get_by(
        Organization,
        secure_code=secure_code,
        is_deleted=False,
        check_permission=False
    )
    if not org:
        abort(404)

    return render_template('pages/organizations/view.html', organization=org)


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
        admin_username = request.form.get('admin_username', 'admin').strip() or 'admin'
        admin_password = request.form.get('admin_password', '').strip() or None

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
                flash('無法自動產生企業代碼，請手動輸入', 'error')

        if not code or not name or not domain_name:
            flash('企業代碼、企業名稱、網域名稱為必填', 'error')
        elif not domain_name.replace('-', '').replace('.', '').isalnum():
            flash('網域名稱只能包含字母、數字、連字號和點', 'error')
        elif admin_password and len(admin_password) < 12:
            flash('管理員密碼長度至少 12 碼', 'error')
        else:
            try:
                org, admin_user = OrganizationService.create_organization(
                    code=code,
                    name=name,
                    display_name=display_name,
                    domain_name=domain_name,
                    description=description,
                    admin_username=admin_username,
                    admin_password=admin_password,
                    created_by=current_user.email
                )
                db.session.commit()

                admin_info = f'{admin_username}@{domain_name}'
                flash(f'已建立企業 {name}，管理員帳號: {admin_info}', 'success')
                return redirect(url_for('organizations.list_orgs'))
            except ValueError as e:
                db.session.rollback()
                flash(str(e), 'error')
            except Exception as e:
                db.session.rollback()
                flash(f'建立失敗: {str(e)}', 'error')

    return render_template('pages/organizations/create.html')


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

        if not name:
            flash('企業名稱為必填', 'error')
        else:
            try:
                org.name = name
                org.display_name = display_name
                org.description = description
                org.is_active = is_active
                db.session.commit()
                flash('已更新企業資料', 'success')
                return redirect(url_for('organizations.list_orgs'))
            except Exception as e:
                db.session.rollback()
                flash(f'更新失敗: {str(e)}', 'error')

    # 查詢未到期的有效合約（狀態 ACTIVE 且結束日期 >= 今天）
    today = date.today()
    active_contracts = Contract.query.filter(
        Contract.org_secure_code == org.secure_code,
        Contract.is_deleted == False,
        Contract.status == 'ACTIVE',
        Contract.end_date >= today
    ).order_by(Contract.end_date.desc()).all()

    return render_template(
        'pages/organizations/edit.html',
        organization=org,
        active_contracts=active_contracts
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
        flash('系統企業不可刪除', 'error')
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
        msg = f'已刪除企業 {org.name}'
        if contract_count > 0:
            msg += f'（含 {contract_count} 份合約）'
        flash(msg, 'success')
        return redirect(url_for('organizations.list_orgs'))
    except Exception as e:
        db.session.rollback()
        flash(f'刪除失敗: {str(e)}', 'error')
        return redirect(url_for('organizations.edit_org', secure_code=secure_code))


# === 合約管理路由 ===

@organizations_bp.route('/contracts/<org_secure_code>/add', methods=['GET', 'POST'])
@system_admin_required
def add_contract(org_secure_code: str):
    """新增合約"""
    org = ResourceGateway.get_by(
        Organization,
        secure_code=org_secure_code,
        is_deleted=False,
        check_permission=False
    )
    if not org:
        abort(404)

    if request.method == 'POST':
        try:
            selected_modules = request.form.getlist('modules')
            modules_config = json.dumps(selected_modules) if selected_modules else None

            contract = Contract(
                org_secure_code=org.secure_code,
                contract_number=Contract.generate_contract_number(),
                name=request.form.get('name', '').strip() or None,
                description=request.form.get('description', '').strip() or None,
                start_date=date.fromisoformat(request.form.get('start_date')),
                end_date=date.fromisoformat(request.form.get('end_date')),
                amount=request.form.get('amount') or None,
                status=request.form.get('status', 'ACTIVE'),
                modules_config=modules_config,
                notes=request.form.get('notes', '').strip() or None,
                created_by_secure_code=current_user.secure_code
            )
            db.session.add(contract)
            db.session.commit()
            flash(f'已新增合約 {contract.contract_number}', 'success')
            return redirect(url_for('organizations.list_orgs', org=org.secure_code))
        except Exception as e:
            db.session.rollback()
            flash(f'新增失敗: {str(e)}', 'error')

    available_modules = LookupService.get_items('INSTALLED_MODULES')

    return render_template(
        'pages/organizations/contract_form.html',
        organization=org,
        contract=None,
        action='add',
        available_modules=available_modules,
        selected_modules=[]
    )


@organizations_bp.route('/contracts/<org_secure_code>/<contract_secure_code>/edit', methods=['GET', 'POST'])
@system_admin_required
def edit_contract(org_secure_code: str, contract_secure_code: str):
    """編輯合約"""
    org = ResourceGateway.get_by(
        Organization,
        secure_code=org_secure_code,
        is_deleted=False,
        check_permission=False
    )
    if not org:
        abort(404)

    contract = ResourceGateway.get_by(
        Contract,
        secure_code=contract_secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False,
        check_permission=False
    )
    if not contract:
        abort(404)

    if request.method == 'POST':
        try:
            selected_modules = request.form.getlist('modules')
            modules_config = json.dumps(selected_modules) if selected_modules else None

            contract.name = request.form.get('name', '').strip() or None
            contract.description = request.form.get('description', '').strip() or None
            contract.start_date = date.fromisoformat(request.form.get('start_date'))
            contract.end_date = date.fromisoformat(request.form.get('end_date'))
            contract.amount = request.form.get('amount') or None
            contract.status = request.form.get('status', 'ACTIVE')
            contract.modules_config = modules_config
            contract.notes = request.form.get('notes', '').strip() or None
            contract.modified_by_secure_code = current_user.secure_code
            contract.modified_at = datetime.utcnow()
            db.session.commit()
            flash('已更新合約', 'success')
            return redirect(url_for('organizations.list_orgs', org=org.secure_code))
        except Exception as e:
            db.session.rollback()
            flash(f'更新失敗: {str(e)}', 'error')

    available_modules = LookupService.get_items('INSTALLED_MODULES')

    selected_modules = []
    if contract.modules_config:
        try:
            selected_modules = json.loads(contract.modules_config)
        except (json.JSONDecodeError, TypeError):
            pass

    return render_template(
        'pages/organizations/contract_form.html',
        organization=org,
        contract=contract,
        action='edit',
        available_modules=available_modules,
        selected_modules=selected_modules
    )


@organizations_bp.route('/contracts/<org_secure_code>/<contract_secure_code>/delete', methods=['POST'])
@system_admin_required
def delete_contract(org_secure_code: str, contract_secure_code: str):
    """刪除合約（軟刪除）"""
    contract = ResourceGateway.get_by(
        Contract,
        secure_code=contract_secure_code,
        org_secure_code=org_secure_code,
        is_deleted=False,
        check_permission=False
    )
    if not contract:
        abort(404)

    try:
        contract.is_deleted = True
        contract.deleted_at = datetime.utcnow()
        db.session.commit()
        flash(f'已刪除合約 {contract.contract_number}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'刪除失敗: {str(e)}', 'error')

    return redirect(url_for('organizations.list_orgs', org=org_secure_code))
