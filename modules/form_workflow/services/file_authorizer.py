"""
FormWorkflow Module - 檔案物件級授權判定

註冊給平台 file_service 的 authorizer，判定用戶是否為
form_attachment 所屬簽核流程（context_id = FwFormInstance.secure_code）的參與者。

參與者定義（與「我的表單」「待簽清單」既有查詢邏輯一致）：
- 發起人：FwFormInstance.applicant_secure_code
- 已簽核者：FwApprovalRecord.approver_secure_code
- 當前待簽者：FwNodeExecutionQueue（WAITING）result['data']['assignees']

admin / 上傳者本人 / 租戶隔離已由 file_service.can_access_file() 上游處理，
此處只判定「流程參與者」。
"""
import logging

from flask import g, has_request_context

logger = logging.getLogger(__name__)


def is_form_participant(user, record) -> bool:
    """
    判定 user 是否為 record（form_attachment）所屬流程實例的參與者。

    Args:
        user: 平台 User 物件
        record: PlatformFile 記錄（context_type='form_attachment'）
    """
    fi_sc = record.context_id
    if not fi_sc:
        # 附件尚未關聯流程實例（如填單中的暫存檔）→ 只有上傳者能碰，
        # 而上傳者已在上游放行，走到這裡一律擋下
        return False

    user_sc = user.secure_code

    # 同一請求內（如 list 逐筆過濾）對同一流程實例只查一次
    cache_key = (user_sc, fi_sc)
    if has_request_context():
        cache = getattr(g, '_fw_file_authz_cache', None)
        if cache is None:
            cache = {}
            g._fw_file_authz_cache = cache
        if cache_key in cache:
            return cache[cache_key]

    result = _check_participant(user_sc, fi_sc, record.org_secure_code)

    if has_request_context():
        g._fw_file_authz_cache[cache_key] = result
    return result


def _check_participant(user_sc: str, fi_sc: str, org_sc: str) -> bool:
    from ..models import FwFormInstance, FwApprovalRecord, FwNodeExecutionQueue
    from .task_authorizer import build_actor, is_pending_assignee

    instance = FwFormInstance.query.filter_by(
        secure_code=fi_sc,
        org_secure_code=org_sc,
    ).first()
    if not instance:
        return False

    # 發起人
    if instance.applicant_secure_code == user_sc:
        return True

    # 已簽核者
    acted = FwApprovalRecord.query.filter_by(
        form_instance_secure_code=fi_sc,
        approver_secure_code=user_sc,
    ).first()
    if acted:
        return True

    # 當前待簽者（assignees 存在節點執行結果 JSON 中）
    waiting_tasks = FwNodeExecutionQueue.query.filter_by(
        form_instance_secure_code=fi_sc,
        org_secure_code=org_sc,
        status='WAITING',
    ).all()
    actor = build_actor(user_sc, org_sc)
    for task in waiting_tasks:
        if is_pending_assignee(task, user_sc, org_sc, actor):
            return True

    return False


def register(file_service):
    """由模組 init_runtime() 呼叫，向平台註冊 authorizer"""
    file_service.register_file_authorizer('form_attachment', is_form_participant)
