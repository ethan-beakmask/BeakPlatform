"""
FormWorkflow Module - Published Form Workflow Model
已發行表單流程配對模型

存放發行時的完整快照，確保執行版本與設計版本分離。
"""
import secrets
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Boolean, Integer, DateTime, JSON, Text, CheckConstraint, event
from sqlalchemy.orm import relationship
from .base import ModuleBaseModel


class FwPublishedFormWorkflow(ModuleBaseModel):
    """
    已發行表單流程配對

    發行時複製表單和流程的完整定義到此表，作為不可修改的執行版本。
    一般用戶使用此表的資料，設計區的修改不會影響已發行的版本。
    """
    __tablename__ = 'fw_published_form_workflows'

    # 組織隔離
    org_secure_code = Column(String(100), nullable=False, index=True)

    # ========== 來源追蹤（知道從哪個設計版本發行）==========
    source_mapping_id = Column(BigInteger, nullable=False, index=True)
    source_mapping_secure_code = Column(String(32), nullable=False, index=True)

    # 表單來源資訊
    source_form_template_id = Column(BigInteger, nullable=False)
    source_form_template_secure_code = Column(String(32), nullable=False)
    source_form_version = Column(String(10))  # 當時的版本
    source_form_revision = Column(BigInteger)  # 當時的 revision

    # 流程來源資訊
    source_workflow_template_id = Column(BigInteger, nullable=False)
    source_workflow_template_secure_code = Column(String(32), nullable=False)
    source_workflow_version = Column(String(10))  # 當時的版本
    source_workflow_revision = Column(BigInteger)  # 當時的 revision

    # ========== 發行資訊 ==========
    publish_version = Column(Integer, default=1, nullable=False)  # 這個 mapping 的第幾次發行
    name = Column(String(255), nullable=False)  # 發行名稱（給用戶看）
    description = Column(Text)  # 發行說明

    # ========== 快照（完整複製，切斷關聯）==========
    form_snapshot = Column(JSON, nullable=False)  # 表單定義快照
    workflow_snapshot = Column(JSON, nullable=False)  # 流程定義快照（含 nodes, edges）

    # ========== 狀態管理 ==========
    # Published: 已發行，一般用戶可使用
    # Suspended: 已停用，不可新建但舊案件繼續跑
    # Archived: 已封存，完全停用
    status = Column(String(20), default='Published', nullable=False, index=True)

    is_used = Column(Boolean, default=False, nullable=False)  # 是否曾被使用過
    first_used_at = Column(DateTime)  # 首次使用時間
    instance_count = Column(Integer, default=0, nullable=False)  # 表單實例數量

    # ========== 稽核欄位 ==========
    published_by = Column(String(100))  # 發行人
    published_by_name = Column(String(100))  # 發行人姓名
    published_at = Column(DateTime, default=datetime.utcnow)  # 發行時間
    suspended_at = Column(DateTime)  # 停用時間
    suspended_by = Column(String(100))  # 停用人
    archived_at = Column(DateTime)  # 封存時間

    # ========== 約束 ==========
    __table_args__ = (
        CheckConstraint(
            "status IN ('Published', 'Suspended', 'Archived')",
            name='fw_published_valid_status'
        ),
    )

    def __repr__(self):
        return f'<FwPublishedFormWorkflow {self.secure_code}: {self.name} v{self.publish_version} ({self.status})>'

    def to_dict(self, include_snapshots=False):
        """
        轉換為字典

        Args:
            include_snapshots: 是否包含完整快照（預設 False，快照可能很大）

        Returns:
            dict
        """
        data = {
            'id': self.id,
            'secure_code': self.secure_code,
            'org_secure_code': self.org_secure_code,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,

            # 來源追蹤
            'source_mapping_id': self.source_mapping_id,
            'source_mapping_secure_code': self.source_mapping_secure_code,

            # 表單來源
            'source_form_template_id': self.source_form_template_id,
            'source_form_template_secure_code': self.source_form_template_secure_code,
            'source_form_version': self.source_form_version,
            'source_form_revision': self.source_form_revision,

            # 流程來源
            'source_workflow_template_id': self.source_workflow_template_id,
            'source_workflow_template_secure_code': self.source_workflow_template_secure_code,
            'source_workflow_version': self.source_workflow_version,
            'source_workflow_revision': self.source_workflow_revision,

            # 發行資訊
            'publish_version': self.publish_version,
            'name': self.name,
            'description': self.description,

            # 狀態
            'status': self.status,
            'is_used': self.is_used,
            'first_used_at': self.first_used_at.isoformat() if self.first_used_at else None,
            'instance_count': self.instance_count,

            # 稽核
            'published_by': self.published_by,
            'published_by_name': self.published_by_name,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'suspended_at': self.suspended_at.isoformat() if self.suspended_at else None,
            'suspended_by': self.suspended_by,
            'archived_at': self.archived_at.isoformat() if self.archived_at else None,
        }

        if include_snapshots:
            data['form_snapshot'] = self.form_snapshot
            data['workflow_snapshot'] = self.workflow_snapshot
        else:
            # 加入簡化資訊
            data['has_form_snapshot'] = self.form_snapshot is not None
            data['has_workflow_snapshot'] = self.workflow_snapshot is not None
            if self.workflow_snapshot:
                graph = self.workflow_snapshot.get('graph', {})
                data['node_count'] = len(graph.get('nodes', []))
                data['edge_count'] = len(graph.get('edges', []))

        return data

    # ========== 狀態操作 ==========

    def mark_as_used(self):
        """標記為已使用並增加實例計數"""
        from app import db
        if not self.is_used:
            self.is_used = True
            self.first_used_at = datetime.utcnow()
        self.instance_count = (self.instance_count or 0) + 1
        db.session.commit()

    def suspend(self, suspended_by=None):
        """
        停用此發行版本

        Args:
            suspended_by: 停用人 secure_code
        """
        from app import db
        if self.status == 'Archived':
            raise ValueError('已封存的版本無法停用')

        self.status = 'Suspended'
        self.suspended_at = datetime.utcnow()
        self.suspended_by = suspended_by
        db.session.commit()

    def reopen(self):
        """重新開放（Suspended → Published）"""
        from app import db
        if self.status != 'Suspended':
            raise ValueError('只有 Suspended 狀態才能重新開放')

        self.status = 'Published'
        self.suspended_at = None
        self.suspended_by = None
        db.session.commit()

    def archive(self):
        """封存此發行版本"""
        from app import db
        if self.status == 'Archived':
            return

        self.status = 'Archived'
        self.archived_at = datetime.utcnow()
        db.session.commit()

    def can_delete(self):
        """
        檢查是否可以刪除

        Returns:
            tuple[bool, str]: (可否刪除, 原因)
        """
        if self.is_used:
            return False, '已被使用過的版本無法刪除'
        if self.status == 'Archived':
            return False, '已封存的版本只能透過 SQL 刪除'
        return True, 'OK'

    # ========== 類別方法 ==========

    @classmethod
    def get_published_for_mapping(cls, mapping_secure_code: str, org_secure_code: str):
        """
        取得指定配對的已發行版本

        Args:
            mapping_secure_code: 配對 secure_code
            org_secure_code: 組織代碼

        Returns:
            FwPublishedFormWorkflow or None: 目前有效的已發行版本
        """
        return cls.query.filter_by(
            source_mapping_secure_code=mapping_secure_code,
            org_secure_code=org_secure_code,
            status='Published',
            is_deleted=False
        ).order_by(cls.publish_version.desc()).first()

    @classmethod
    def get_all_versions_for_mapping(cls, mapping_secure_code: str, org_secure_code: str):
        """
        取得指定配對的所有發行版本

        Args:
            mapping_secure_code: 配對 secure_code
            org_secure_code: 組織代碼

        Returns:
            list[FwPublishedFormWorkflow]
        """
        return cls.query.filter_by(
            source_mapping_secure_code=mapping_secure_code,
            org_secure_code=org_secure_code,
            is_deleted=False
        ).order_by(cls.publish_version.desc()).all()

    @classmethod
    def create_from_mapping(cls, mapping, form_template, workflow_template, published_by=None, published_by_name=None):
        """
        從配對建立已發行版本

        Args:
            mapping: FwFormWorkflowMapping 實例
            form_template: FwFormTemplate 實例
            workflow_template: FwWorkflowTemplate 實例
            published_by: 發行人 secure_code
            published_by_name: 發行人姓名

        Returns:
            FwPublishedFormWorkflow
        """
        # 計算這個 mapping 的下一個版本號
        latest = cls.query.filter_by(
            source_mapping_secure_code=mapping.secure_code
        ).order_by(cls.publish_version.desc()).first()

        next_version = (latest.publish_version + 1) if latest else 1

        return cls(
            secure_code=secrets.token_urlsafe(16),
            org_secure_code=mapping.org_secure_code,

            # 來源追蹤
            source_mapping_id=mapping.id,
            source_mapping_secure_code=mapping.secure_code,

            # 表單來源
            source_form_template_id=form_template.id,
            source_form_template_secure_code=form_template.secure_code,
            source_form_version=form_template.version,
            source_form_revision=form_template.revision,

            # 流程來源
            source_workflow_template_id=workflow_template.id,
            source_workflow_template_secure_code=workflow_template.secure_code,
            source_workflow_version=workflow_template.version,
            source_workflow_revision=workflow_template.revision,

            # 發行資訊
            publish_version=next_version,
            name=f'{form_template.name} + {workflow_template.name}',
            description=f'表單: {form_template.name} ({form_template.version})\n流程: {workflow_template.name} ({workflow_template.version})',

            # 快照
            form_snapshot={
                'name': form_template.name,
                'code': form_template.code,
                'version': form_template.version,
                'schema': form_template.schema,
                'description': form_template.description,
            },
            workflow_snapshot={
                'name': workflow_template.name,
                'code': workflow_template.code,
                'version': workflow_template.version,
                'graph': workflow_template.graph,
                'cytoscape_config': workflow_template.cytoscape_config,
                'description': workflow_template.description,
            },

            # 狀態
            status='Published',
            published_by=published_by,
            published_by_name=published_by_name,
            published_at=datetime.utcnow(),
        )


# 自動生成 secure_code
@event.listens_for(FwPublishedFormWorkflow, 'before_insert')
def generate_published_secure_code(mapper, connection, target):
    """插入前自動生成 secure_code"""
    if not target.secure_code:
        target.secure_code = secrets.token_urlsafe(16)
