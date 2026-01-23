"""
BeakMask Conglomerate Service
集團服務 - 負責集團的 CRUD 和企業歸屬管理
"""
import secrets
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy import or_

from ..models.conglomerate import Conglomerate
from ..models.organization import Organization
from ..models.conglomerate_log import ConglomerateLog
from .. import db


class ConglomerateService:
    """
    集團服務

    負責：
    1. 集團 CRUD
    2. 企業加入/移出集團
    3. 操作日誌記錄
    """

    @classmethod
    def generate_code(cls) -> str:
        """
        產生集團代碼

        格式: CG + 8位隨機字串 (大寫英數)
        """
        return 'CG' + secrets.token_hex(4).upper()

    @classmethod
    def list_conglomerates(
        cls,
        include_inactive: bool = False
    ) -> List[Conglomerate]:
        """
        取得所有集團

        Args:
            include_inactive: 是否包含停用的集團

        Returns:
            集團列表
        """
        query = Conglomerate.query.filter(
            Conglomerate.is_deleted == False
        )

        if not include_inactive:
            query = query.filter(Conglomerate.is_active == True)

        return query.order_by(Conglomerate.name).all()

    @classmethod
    def get_conglomerate(cls, secure_code: str) -> Optional[Conglomerate]:
        """取得單一集團"""
        return Conglomerate.query.filter_by(
            secure_code=secure_code,
            is_deleted=False
        ).first()

    @classmethod
    def get_conglomerate_by_code(cls, code: str) -> Optional[Conglomerate]:
        """以 code 取得集團"""
        return Conglomerate.query.filter_by(
            code=code,
            is_deleted=False
        ).first()

    @classmethod
    def create_conglomerate(
        cls,
        name: str,
        org_secure_codes: List[str],
        operator_email: str,
        description: Optional[str] = None
    ) -> Tuple[Conglomerate, List[Organization]]:
        """
        建立集團

        Args:
            name: 集團名稱
            org_secure_codes: 要加入集團的企業 secure_code 列表
            operator_email: 操作者信箱
            description: 集團描述

        Returns:
            (集團, 加入的企業列表)

        Raises:
            ValueError: 企業數量不足或企業不存在
        """
        if len(org_secure_codes) < 2:
            raise ValueError('至少需要選擇兩家企業才能成立集團')

        # 取得企業
        orgs = Organization.query.filter(
            Organization.secure_code.in_(org_secure_codes),
            Organization.is_deleted == False,
            Organization.domain_name != 'system.local'  # 系統企業不可加入集團
        ).all()

        if len(orgs) < 2:
            raise ValueError('有效企業數量不足（系統企業不可加入集團）')

        # 檢查這些企業是否已屬於其他集團
        for org in orgs:
            if org.conglomerate_secure_code:
                raise ValueError(f'企業 {org.name} 已屬於其他集團')

        # 建立集團
        conglomerate = Conglomerate(
            code=cls.generate_code(),
            name=name,
            description=description,
            is_active=True
        )
        db.session.add(conglomerate)
        db.session.flush()  # 取得 secure_code

        # 將企業加入集團
        for org in orgs:
            org.conglomerate_secure_code = conglomerate.secure_code
            # 記錄日誌
            cls._log_action(
                conglomerate.secure_code,
                org.secure_code,
                'JOIN',
                operator_email,
                f'企業 {org.name} 加入集團 {name}'
            )

        return conglomerate, orgs

    @classmethod
    def update_conglomerate(
        cls,
        secure_code: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Optional[Conglomerate]:
        """
        更新集團資料

        Args:
            secure_code: 集團識別碼
            name: 新名稱
            description: 新描述
            is_active: 是否啟用

        Returns:
            更新後的集團，若不存在則返回 None
        """
        conglomerate = cls.get_conglomerate(secure_code)
        if not conglomerate:
            return None

        if name is not None:
            conglomerate.name = name
        if description is not None:
            conglomerate.description = description
        if is_active is not None:
            conglomerate.is_active = is_active

        return conglomerate

    @classmethod
    def delete_conglomerate(
        cls,
        secure_code: str,
        operator_email: str
    ) -> bool:
        """
        刪除集團（解散集團，所有企業退出）

        Args:
            secure_code: 集團識別碼
            operator_email: 操作者信箱

        Returns:
            是否成功刪除
        """
        conglomerate = cls.get_conglomerate(secure_code)
        if not conglomerate:
            return False

        # 將所有企業移出集團
        orgs = Organization.query.filter_by(
            conglomerate_secure_code=secure_code,
            is_deleted=False
        ).all()

        for org in orgs:
            org.conglomerate_secure_code = None
            cls._log_action(
                secure_code,
                org.secure_code,
                'LEAVE',
                operator_email,
                f'集團 {conglomerate.name} 解散，企業 {org.name} 退出'
            )

        # 軟刪除集團
        conglomerate.is_deleted = True
        conglomerate.deleted_at = datetime.utcnow()
        conglomerate.is_active = False

        return True

    @classmethod
    def add_organizations(
        cls,
        conglomerate_secure_code: str,
        org_secure_codes: List[str],
        operator_email: str
    ) -> List[Organization]:
        """
        將企業加入集團

        Args:
            conglomerate_secure_code: 集團識別碼
            org_secure_codes: 企業 secure_code 列表
            operator_email: 操作者信箱

        Returns:
            成功加入的企業列表

        Raises:
            ValueError: 集團不存在
        """
        conglomerate = cls.get_conglomerate(conglomerate_secure_code)
        if not conglomerate:
            raise ValueError('集團不存在')

        orgs = Organization.query.filter(
            Organization.secure_code.in_(org_secure_codes),
            Organization.is_deleted == False,
            Organization.domain_name != 'system.local',  # 系統企業不可加入集團
            Organization.conglomerate_secure_code == None  # 未加入其他集團
        ).all()

        for org in orgs:
            org.conglomerate_secure_code = conglomerate_secure_code
            cls._log_action(
                conglomerate_secure_code,
                org.secure_code,
                'JOIN',
                operator_email,
                f'企業 {org.name} 加入集團 {conglomerate.name}'
            )

        return orgs

    @classmethod
    def remove_organizations(
        cls,
        conglomerate_secure_code: str,
        org_secure_codes: List[str],
        operator_email: str
    ) -> Tuple[List[Organization], bool]:
        """
        將企業移出集團

        Args:
            conglomerate_secure_code: 集團識別碼
            org_secure_codes: 企業 secure_code 列表
            operator_email: 操作者信箱

        Returns:
            (移出的企業列表, 集團是否因此解散)

        Raises:
            ValueError: 集團不存在
        """
        conglomerate = cls.get_conglomerate(conglomerate_secure_code)
        if not conglomerate:
            raise ValueError('集團不存在')

        orgs = Organization.query.filter(
            Organization.secure_code.in_(org_secure_codes),
            Organization.conglomerate_secure_code == conglomerate_secure_code,
            Organization.is_deleted == False
        ).all()

        for org in orgs:
            org.conglomerate_secure_code = None
            cls._log_action(
                conglomerate_secure_code,
                org.secure_code,
                'LEAVE',
                operator_email,
                f'企業 {org.name} 退出集團 {conglomerate.name}'
            )

        # 檢查剩餘企業數量
        remaining = Organization.query.filter_by(
            conglomerate_secure_code=conglomerate_secure_code,
            is_deleted=False
        ).count()

        dissolved = False
        if remaining < 2:
            # 集團企業不足 2 家，自動解散
            dissolved = cls.delete_conglomerate(conglomerate_secure_code, operator_email)

        return orgs, dissolved

    @classmethod
    def update_organization_memberships(
        cls,
        conglomerate_secure_code: str,
        new_org_secure_codes: List[str],
        operator_email: str
    ) -> Dict[str, Any]:
        """
        更新集團的企業成員（設定模式：直接指定最終成員）

        Args:
            conglomerate_secure_code: 集團識別碼
            new_org_secure_codes: 新的企業成員 secure_code 列表
            operator_email: 操作者信箱

        Returns:
            {added: [...], removed: [...], dissolved: bool}

        Raises:
            ValueError: 集團不存在或成員不足
        """
        conglomerate = cls.get_conglomerate(conglomerate_secure_code)
        if not conglomerate:
            raise ValueError('集團不存在')

        if len(new_org_secure_codes) < 2:
            raise ValueError('集團至少需要兩家企業')

        # 取得現有成員
        current_orgs = Organization.query.filter_by(
            conglomerate_secure_code=conglomerate_secure_code,
            is_deleted=False
        ).all()
        current_codes = {org.secure_code for org in current_orgs}
        new_codes = set(new_org_secure_codes)

        # 計算差異
        to_add = new_codes - current_codes
        to_remove = current_codes - new_codes

        added = []
        removed = []

        # 新增成員
        if to_add:
            added = cls.add_organizations(
                conglomerate_secure_code,
                list(to_add),
                operator_email
            )

        # 移除成員
        if to_remove:
            removed, _ = cls.remove_organizations(
                conglomerate_secure_code,
                list(to_remove),
                operator_email
            )

        return {
            'added': added,
            'removed': removed,
            'dissolved': False
        }

    @classmethod
    def _log_action(
        cls,
        conglomerate_secure_code: str,
        org_secure_code: str,
        action: str,
        operator_email: str,
        description: str
    ) -> None:
        """記錄集團操作日誌"""
        log = ConglomerateLog(
            conglomerate_secure_code=conglomerate_secure_code,
            org_secure_code=org_secure_code,
            action=action,
            operator_email=operator_email,
            description=description
        )
        db.session.add(log)

    @classmethod
    def get_logs(
        cls,
        conglomerate_secure_code: Optional[str] = None,
        org_secure_code: Optional[str] = None,
        limit: int = 100
    ) -> List['ConglomerateLog']:
        """
        取得集團操作日誌

        Args:
            conglomerate_secure_code: 按集團篩選
            org_secure_code: 按企業篩選
            limit: 最大筆數

        Returns:
            日誌列表（最新優先）
        """
        query = ConglomerateLog.query

        if conglomerate_secure_code:
            query = query.filter_by(conglomerate_secure_code=conglomerate_secure_code)
        if org_secure_code:
            query = query.filter_by(org_secure_code=org_secure_code)

        return query.order_by(ConglomerateLog.created_at.desc()).limit(limit).all()
