"""
FormWorkflow Module - Workflow Template Model
工作流模板
"""
from sqlalchemy import Column, String, Text, Boolean, Integer, ForeignKey, BigInteger
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from .base import ModuleBaseModel


class FwWorkflowTemplate(ModuleBaseModel):
    """
    工作流模板

    儲存 Cytoscape.js 格式的流程圖定義。
    """
    __tablename__ = 'fw_workflow_templates'

    # 關聯的表單模板
    form_template_secure_code = Column(String(32), nullable=True, index=True)

    # 基本資訊
    code = Column(String(100), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True, index=True)
    category_secure_code = Column(String(32), nullable=True, index=True)

    # Cytoscape.js 流程圖
    graph = Column(JSON, nullable=False)  # 舊格式
    cytoscape_config = Column(JSON, nullable=True)  # 新格式

    # 版本控制
    version = Column(String(2), default='AA')
    revision = Column(BigInteger, default=0)

    # 縮圖
    thumbnail_2x1 = Column(Text, nullable=True)
    thumbnail_1x1 = Column(Text, nullable=True)
    thumbnail_1x2 = Column(Text, nullable=True)

    # 狀態
    is_published = Column(Boolean, default=False, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_protected = Column(Boolean, default=False, nullable=False)

    # 權限控制
    permission_type = Column(String(20), default='org', nullable=False)
    owner_secure_code = Column(String(50), nullable=True, index=True)
    allowed_editors = Column(JSON, nullable=True)

    # 建立者/編輯者
    created_by_secure_code = Column(String(32), nullable=True)
    created_by_name = Column(String(100), nullable=True)
    updated_by_secure_code = Column(String(32), nullable=True)
    updated_by_name = Column(String(100), nullable=True)

    # 子流程相關
    is_subprocess = Column(Boolean, default=False, nullable=False, index=True)
    parent_workflow_secure_code = Column(String(32), nullable=True, index=True)
    parent_workflow_id = Column(BigInteger, nullable=True, index=True)  # 父流程 ID（用於專屬子流程）

    def __repr__(self):
        return f'<FwWorkflowTemplate {self.code}: {self.name}>'

    def to_dict(self, include_graph=True):
        """轉換為字典"""
        data = super().to_dict()
        data.update({
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'category_secure_code': self.category_secure_code,
            'version': self.version,
            'revision': self.revision,
            'thumbnail_2x1': self.thumbnail_2x1,
            'is_published': self.is_published,
            'is_active': self.is_active,
            'is_protected': self.is_protected,
            'is_subprocess': self.is_subprocess,
            'parent_workflow_secure_code': self.parent_workflow_secure_code,
            'form_template_secure_code': self.form_template_secure_code,
            'owner_secure_code': self.owner_secure_code,
            'created_by_secure_code': self.created_by_secure_code,
            'created_by_name': self.created_by_name,
            'updated_by_secure_code': self.updated_by_secure_code,
            'updated_by_name': self.updated_by_name,
        })

        if include_graph:
            data['graph'] = self.graph
            data['cytoscape_config'] = self.cytoscape_config
        else:
            data['has_graph'] = self.graph is not None
            data['node_count'] = len(self.graph.get('nodes', [])) if self.graph else 0
            data['edge_count'] = len(self.graph.get('edges', [])) if self.graph else 0

        return data

    def can_publish(self):
        """檢查是否可以發布"""
        if not self.graph:
            return False, '工作流 graph 不可為空'

        nodes = self.graph.get('nodes', [])
        if not nodes:
            return False, '工作流必須包含至少一個節點'

        # 檢查 Start 節點
        start_nodes = [n for n in nodes if n.get('type', '').upper() == 'START']
        if not start_nodes:
            return False, '工作流必須包含一個 Start 節點'
        if len(start_nodes) > 1:
            return False, '工作流只能有一個 Start 節點'

        # 檢查 End 節點
        end_nodes = [n for n in nodes if n.get('type', '').upper() == 'END']
        if not end_nodes:
            return False, '工作流必須包含至少一個 End 節點'

        return True, 'OK'
