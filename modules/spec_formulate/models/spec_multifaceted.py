"""
Spec Multifaceted Model - 多面向規格定義

核心設計：
- fields JSONB 每個欄位包含 core（通用）+ facets（格式專屬）
- active_facets 追蹤已操作過的格式
- linked_form_template_sc / linked_sql_table 標示關聯但不影響 SPEC 運作
"""
import secrets
from sqlalchemy import Column, String, Integer, Text, JSON, event
from .base import ModuleBaseModel


class FwSpecMultifaceted(ModuleBaseModel):
    """
    多面向規格定義

    每個 SPEC 是一組欄位定義，透過 data_class 抽象資料類別
    橋接 PostgreSQL / FormIO / Excel / CSV 四種格式的差異。

    fields JSONB 結構:
    [
        {
            "field_key": "order_id",
            "label": "訂單編號",
            "sort_order": 0,
            "description": "主鍵",
            "core": {
                "data_class": "integer",
                "required": true,
                "is_pii": false,
                "default_value": null
            },
            "facets": {
                "postgresql": { "pg_type": "SERIAL", "primary_key": true, ... },
                "formio": { "component_type": "number", ... },
                "excel": { "format": "#,##0", ... },
                "csv": { "quote_mode": "auto" }
            }
        }
    ]
    """
    __tablename__ = 'fw_spec_multifaceted'

    org_secure_code = Column(String(100), nullable=False, index=True)

    # 規格名稱（必填）
    name = Column(String(200), nullable=False)

    # 資料表名稱（英文 snake_case，加 spec_ 前綴，用於 PostgreSQL 建表）
    table_name = Column(String(100), nullable=True)

    # 描述
    description = Column(Text)

    # 版本（每次儲存遞增）
    version = Column(Integer, nullable=False, default=1)

    # 欄位定義 (JSONB array, core + facets 分層結構)
    fields = Column(JSON, nullable=False, default=list)

    # 已操作過的格式清單，如 ["postgresql", "formio"]
    active_facets = Column(JSON, nullable=False, default=list)

    # 狀態: active / archived
    status = Column(String(20), nullable=False, default='active')

    # 關聯表單模板（nullable，綁定後記錄）
    linked_form_template_sc = Column(String(32), nullable=True)

    # 關聯 SQL 表名（nullable，套用後記錄）
    linked_sql_table = Column(String(100), nullable=True)

    # 修改者
    last_modified_by = Column(String(32))
    last_modified_by_name = Column(String(200))

    def __repr__(self):
        return (
            f'<FwSpecMultifaceted name={self.name!r} '
            f'v{self.version} ({self.status})>'
        )

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'name': self.name,
            'table_name': self.table_name,
            'description': self.description,
            'version': self.version,
            'fields': self.fields or [],
            'active_facets': self.active_facets or [],
            'status': self.status,
            'linked_form_template_sc': self.linked_form_template_sc,
            'linked_sql_table': self.linked_sql_table,
            'last_modified_by': self.last_modified_by,
            'last_modified_by_name': self.last_modified_by_name,
        })
        return base

    def get_field_keys(self):
        """取得所有 field_key 列表"""
        return [f['field_key'] for f in (self.fields or []) if f.get('field_key')]

    def get_field_by_key(self, field_key):
        """根據 field_key 取得欄位定義"""
        for f in (self.fields or []):
            if f.get('field_key') == field_key:
                return f
        return None

    def has_facet(self, facet_name):
        """檢查是否已操作過指定格式"""
        return facet_name in (self.active_facets or [])

    def add_facet(self, facet_name):
        """標記已操作過的格式"""
        facets = list(self.active_facets or [])
        if facet_name not in facets:
            facets.append(facet_name)
            self.active_facets = facets


@event.listens_for(FwSpecMultifaceted, 'before_insert')
def generate_mf_secure_code(mapper, connection, target):
    if not target.secure_code:
        target.secure_code = secrets.token_urlsafe(16)
