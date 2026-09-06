"""
FormWorkflow Module - Approval Record Model
簽核記錄
"""
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime

from .base import ModuleBaseModel


class FwApprovalRecord(ModuleBaseModel):
    """
    簽核記錄

    記錄每一筆簽核動作。
    """
    __tablename__ = 'fw_approval_records'

    # 關聯的表單實例
    form_instance_secure_code = Column(String(32), nullable=False, index=True)
    workflow_instance_secure_code = Column(String(32), nullable=True, index=True)

    # 節點資訊
    node_id = Column(String(100), nullable=False)
    node_name = Column(String(200), nullable=True)
    node_queue_secure_code = Column(String(32), nullable=True, index=True)

    # 簽核人（使用 secure_code）
    approver_secure_code = Column(String(32), nullable=True, index=True)
    approver_name = Column(String(200), nullable=True)
    approver_dept = Column(String(200), nullable=True)

    # 代理人資訊
    delegate_from_secure_code = Column(String(32), nullable=True)
    delegate_from_name = Column(String(200), nullable=True)
    # 以 proxy／standby 身分命中的角色 code（PF-251）；regular 或快照命中時 NULL。2026-09-06 之前的舊列存的是缺席順位角色（DEPT_DEPUTY／PROXY1／PROXY2）
    acted_as_role_code = Column(String(50), nullable=True)
    acted_as_kind = Column(String(10), nullable=True)

    # 簽核動作：PENDING, APPROVED, REJECTED, TRANSFERRED, CANCELLED
    action = Column(String(50), nullable=False, index=True)

    # 簽核意見
    comment = Column(Text, nullable=True)

    # 時間
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    acted_at = Column(DateTime, nullable=True)

    # 動作名稱對應
    ACTION_NAMES = {
        'PENDING': '待簽核',
        'APPROVED': '核准',
        'REJECTED': '退回',
        'TRANSFERRED': '轉交',
        'CANCELLED': '取消',
        'timeout': '逾時自動處理',   # 簽核節點逾時由系統自動採用逾時去向（PF-229 第三期第 2 項）
        'no_assignee': '找不到簽核人，退回申請人',   # 簽核節點解析不到簽核者時由系統退回申請人重送（PF-226）
    }

    def __repr__(self):
        return f'<FwApprovalRecord {self.form_instance_secure_code}/{self.node_id}: {self.action}>'

    def to_dict(self):
        """轉換為字典"""
        data = super().to_dict()
        data.update({
            'form_instance_secure_code': self.form_instance_secure_code,
            'node_id': self.node_id,
            'node_name': self.node_name,
            'approver_name': self.approver_name,
            'approver_dept': self.approver_dept,
            'delegate_from_secure_code': self.delegate_from_secure_code,
            'delegate_from_name': self.delegate_from_name,
            'acted_as_role_code': self.acted_as_role_code,
            'acted_as_kind': self.acted_as_kind,
            'action': self.action,
            'action_name': self.ACTION_NAMES.get(self.action, self.action),
            'comment': self.comment,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'acted_at': self.acted_at.isoformat() if self.acted_at else None,
        })
        return data

    def approve(self, comment=None):
        """核准"""
        self.action = 'APPROVED'
        self.comment = comment
        self.acted_at = datetime.utcnow()

    def reject(self, comment=None):
        """退回"""
        self.action = 'REJECTED'
        self.comment = comment
        self.acted_at = datetime.utcnow()

    def transfer(self, to_user_secure_code, to_user_name, comment=None):
        """轉交"""
        self.action = 'TRANSFERRED'
        self.comment = comment
        self.acted_at = datetime.utcnow()
        # 轉交後需建立新的 ApprovalRecord
