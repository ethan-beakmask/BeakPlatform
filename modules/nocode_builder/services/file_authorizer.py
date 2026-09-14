"""
NocodeBuilder Module - 檔案物件級授權判定

註冊給平台 file_service 的 authorizer，判定用戶是否可存取
subsystem_file（context_id = DcCrudView.secure_code，即 datalist 附件所屬視圖）。

判定等級對齊模組現行 CRUD API（query_rows / get_row）的授權：
`@module_access_required('nocode_builder', False)` = 企業有模組合約，
加上 view 必須存在於用戶所在企業（租戶隔離）。

admin / 上傳者本人已由 file_service.can_access_file() 上游放行。
"""
import logging

logger = logging.getLogger(__name__)


def can_access_subsystem_file(user, record) -> bool:
    """
    判定 user 是否可存取 record（subsystem_file）。

    Args:
        user: 平台 User 物件
        record: PlatformFile 記錄（context_type='subsystem_file'）
    """
    from app.services.module_access_service import ModuleAccessService
    from ..models import DcCrudView

    # 企業須有 nocode_builder 模組合約（同 CRUD API 的 check_acl=False 等級）
    if not ModuleAccessService.check_module_contract(user, 'nocode_builder'):
        return False

    view_sc = record.context_id
    if not view_sc:
        # 未關聯任何 view 的孤兒附件 → 只有上傳者/admin（上游已放行）能碰
        return False

    view = DcCrudView.query.filter_by(
        secure_code=view_sc,
        org_secure_code=record.org_secure_code,
        is_deleted=False,
    ).first()
    return view is not None


def register(file_service):
    """由模組 init_runtime() 呼叫，向平台註冊 authorizer"""
    file_service.register_file_authorizer('subsystem_file', can_access_subsystem_file)
