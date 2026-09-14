"""
Node showcase demo inventory model.

This table backs the SysSqlExecutor showcase forms. It is demo data, but the
table itself is part of the installed schema so fresh installs can run the
showcase without ad hoc DDL from provisioning scripts.
"""
from sqlalchemy import Column, Index, Numeric, String, text

from .base import BaseModel


class FwDemoInventory(BaseModel):
    """Demo inventory rows used by the node showcase SQL procedures."""

    __tablename__ = 'fw_demo_inventory'

    org_secure_code = Column(String(32), nullable=False, index=True)
    item_code = Column(String(64), nullable=False)
    item_name = Column(String(200), nullable=False)
    qty_on_hand = Column(Numeric(14, 2), nullable=False, default=0)
    safety_qty = Column(Numeric(14, 2), nullable=False, default=0)
    unit = Column(String(20), nullable=False, default='PCS')

    __table_args__ = (
        Index(
            'ux_fw_demo_inventory_org_item',
            'org_secure_code',
            'item_code',
            unique=True,
            postgresql_where=text('is_deleted = false'),
        ),
    )
