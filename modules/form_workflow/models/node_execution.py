"""
FormWorkflow Module - Node Execution Queue Model
節點執行隊列
"""
from datetime import datetime, timedelta
from sqlalchemy import Column, String, Text, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB

from .base import ModuleBaseModel

# 簽核鎖定逾時（分鐘）
APPROVAL_LOCK_TIMEOUT_MINUTES = 10


class FwNodeExecutionQueue(ModuleBaseModel):
    """
    節點執行隊列

    用於背景執行工作流節點。
    """
    __tablename__ = 'fw_node_execution_queue'

    # 關聯的工作流實例
    workflow_instance_secure_code = Column(String(32), nullable=False, index=True)
    form_instance_secure_code = Column(String(32), nullable=True, index=True)

    # 子流程關聯
    calling_instance_code = Column(String(32), nullable=True, index=True)  # 調用方流程實例
    parent_node_id = Column(String(100), nullable=True)                     # 父節點 ID

    # 節點資訊
    node_id = Column(String(100), nullable=False)
    node_type = Column(String(50), nullable=False, index=True)
    node_name = Column(String(200), nullable=True)
    node_config = Column(JSONB, default=dict)
    priority = Column(Integer, default=5, nullable=False)

    # 執行狀態：PENDING, RUNNING, SUCCESS, FAILED, CANCELLED, WAITING
    status = Column(String(50), default='PENDING', nullable=False, index=True)

    # 重試資訊
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)

    # 執行結果
    result = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)

    # 時間
    scheduled_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Worker 資訊
    worker_id = Column(String(100), nullable=True)
    process_id = Column(Integer, nullable=True)

    # 簽核鎖定（防止並行簽核衝突）
    locked_by = Column(String(32), nullable=True, comment='鎖定者 user_secure_code')
    locked_at = Column(DateTime, nullable=True, comment='鎖定時間 (UTC)')

    # 狀態名稱對應
    STATUS_NAMES = {
        'PENDING': '等待執行',
        'RUNNING': '執行中',
        'SUCCESS': '執行成功',
        'FAILED': '執行失敗',
        'CANCELLED': '已取消',
        'WAITING': '等待條件',
    }

    def __repr__(self):
        return f'<FwNodeExecutionQueue {self.node_type}/{self.node_id}: {self.status}>'

    def to_dict(self):
        """轉換為字典"""
        data = super().to_dict()
        data.update({
            'workflow_instance_secure_code': self.workflow_instance_secure_code,
            'node_id': self.node_id,
            'node_type': self.node_type,
            'node_name': self.node_name,
            'status': self.status,
            'status_name': self.STATUS_NAMES.get(self.status, self.status),
            'retry_count': self.retry_count,
            'error_message': self.error_message,
        })

        if self.scheduled_at:
            data['scheduled_at'] = self.scheduled_at.isoformat()
        if self.started_at:
            data['started_at'] = self.started_at.isoformat()
        if self.completed_at:
            data['completed_at'] = self.completed_at.isoformat()

        return data

    def start(self, worker_id=None, process_id=None):
        """開始執行"""
        self.status = 'RUNNING'
        self.started_at = datetime.utcnow()
        self.worker_id = worker_id
        self.process_id = process_id

    def success(self, result=None):
        """執行成功"""
        self.status = 'SUCCESS'
        self.result = result
        self.completed_at = datetime.utcnow()

    def fail(self, error_message):
        """執行失敗"""
        self.retry_count += 1
        if self.retry_count >= self.max_retries:
            self.status = 'FAILED'
        else:
            self.status = 'PENDING'  # 重試
        self.error_message = error_message
        self.completed_at = datetime.utcnow()

    def cancel(self):
        """取消"""
        self.status = 'CANCELLED'
        self.completed_at = datetime.utcnow()

    def wait(self):
        """等待條件"""
        self.status = 'WAITING'

    # ---- 簽核鎖定 ----

    @property
    def is_locked(self):
        """判斷是否被有效鎖定（未逾時）"""
        if not self.locked_by or not self.locked_at:
            return False
        deadline = self.locked_at + timedelta(minutes=APPROVAL_LOCK_TIMEOUT_MINUTES)
        return datetime.utcnow() < deadline

    @property
    def lock_remaining_seconds(self):
        """鎖定剩餘秒數，已逾期回傳 0"""
        if not self.locked_by or not self.locked_at:
            return 0
        deadline = self.locked_at + timedelta(minutes=APPROVAL_LOCK_TIMEOUT_MINUTES)
        remaining = (deadline - datetime.utcnow()).total_seconds()
        return max(0, int(remaining))

    def acquire_lock(self, user_secure_code):
        """取得鎖定"""
        self.locked_by = user_secure_code
        self.locked_at = datetime.utcnow()

    def release_lock(self):
        """釋放鎖定"""
        self.locked_by = None
        self.locked_at = None
