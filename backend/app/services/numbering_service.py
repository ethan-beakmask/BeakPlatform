"""
用戶編號產生服務

核心演算法：
1. 讀取規則的 elements 配置
2. 按 order 排序元素
3. 依序產生各元素值
4. 處理序號進位邏輯（序號滿→前綴進位→後綴進位→循環）
"""
from datetime import datetime
from typing import List, Optional, Tuple
from sqlalchemy import text

from .. import db
from ..models import (
    UserNumberingRule,
    UserNumberingCounter,
    UsedUserNumber,
    NumberingElementType,
    NumberingResetPeriod
)


class NumberingService:
    """編號產生服務"""

    @classmethod
    def get_next_number(
        cls,
        rule: UserNumberingRule,
        consume: bool = False
    ) -> str:
        """
        取得下一個可用編號

        Args:
            rule: 編號規則
            consume: 是否消耗此編號（True 時會遞增計數器並記錄）

        Returns:
            str: 產生的編號

        Raises:
            ValueError: 當所有編號都已用完時
        """
        components = rule.get_components()
        period_key = cls._get_period_key(components)

        # 取得或建立計數器（使用鎖定避免並發）
        counter = cls._get_or_create_counter(rule, period_key, lock=consume)

        # 計算最大嘗試次數（防止無限迴圈）
        max_attempts = cls._calculate_max_numbers(components)

        # 持續尋找直到找到可用編號
        current_state = {
            'prefix_index': counter.prefix_index,
            'suffix_index': counter.suffix_index,
            'current_seq': counter.current_seq
        }
        attempts = 0

        while attempts < max_attempts:
            # 計算下一個序號狀態
            next_state = cls._calculate_next_state_from_dict(current_state, components)

            # 組合編號
            number = cls._compose_number(components, next_state)

            # 檢查編號是否已被使用
            if cls.is_number_available(rule.org_secure_code, number):
                # 找到可用編號
                if consume:
                    # 更新計數器
                    counter.prefix_index = next_state['prefix_index']
                    counter.suffix_index = next_state['suffix_index']
                    counter.current_seq = next_state['current_seq']
                    counter.updated_at = datetime.utcnow()

                    # 記錄已使用編號
                    UsedUserNumber.record_number(
                        org_secure_code=rule.org_secure_code,
                        number=number,
                        rule_secure_code=rule.secure_code
                    )

                    db.session.commit()

                return number

            # 繼續尋找下一個
            current_state = next_state
            attempts += 1

        # 所有編號都已用完
        raise ValueError(f'編號規則「{rule.name}」的所有編號都已用完')

    @classmethod
    def get_next_number_with_detail(
        cls,
        rule: UserNumberingRule,
        consume: bool = False
    ) -> dict:
        """
        取得下一個可用編號，同時回傳裸序號

        Returns:
            dict: {
                'number': str,       # 格式化後的完整編號
                'current_seq': int,  # 裸序號（序號元素的值）
            }

        Raises:
            ValueError: 當所有編號都已用完時
        """
        components = rule.get_components()
        period_key = cls._get_period_key(components)

        counter = cls._get_or_create_counter(rule, period_key, lock=consume)
        max_attempts = cls._calculate_max_numbers(components)

        current_state = {
            'prefix_index': counter.prefix_index,
            'suffix_index': counter.suffix_index,
            'current_seq': counter.current_seq
        }
        attempts = 0

        while attempts < max_attempts:
            next_state = cls._calculate_next_state_from_dict(current_state, components)
            number = cls._compose_number(components, next_state)

            if cls.is_number_available(rule.org_secure_code, number):
                if consume:
                    counter.prefix_index = next_state['prefix_index']
                    counter.suffix_index = next_state['suffix_index']
                    counter.current_seq = next_state['current_seq']
                    counter.updated_at = datetime.utcnow()

                    UsedUserNumber.record_number(
                        org_secure_code=rule.org_secure_code,
                        number=number,
                        rule_secure_code=rule.secure_code
                    )

                    db.session.flush()

                return {
                    'number': number,
                    'current_seq': next_state['current_seq'],
                }

            current_state = next_state
            attempts += 1

        raise ValueError(f'編號規則「{rule.name}」的所有編號都已用完')

    @classmethod
    def _calculate_max_numbers(cls, components: List[dict]) -> int:
        """計算規則可產生的最大編號數量"""
        seq_config = None
        prefix_config = None
        suffix_config = None

        for comp in components:
            if comp.get('type') == NumberingElementType.SEQUENCE:
                seq_config = comp
            elif comp.get('type') == NumberingElementType.PREFIX:
                prefix_config = comp
            elif comp.get('type') == NumberingElementType.SUFFIX:
                suffix_config = comp

        if seq_config is None:
            return 1

        digits = seq_config.get('digits', 4)
        start = seq_config.get('start', 1)
        max_seq = 10 ** digits - start  # 可用序號數量

        prefix_count = len(prefix_config.get('values', [])) if prefix_config else 1
        suffix_count = len(suffix_config.get('values', [])) if suffix_config else 1

        # 至少要有 1
        prefix_count = max(1, prefix_count)
        suffix_count = max(1, suffix_count)

        return max_seq * prefix_count * suffix_count

    @classmethod
    def preview_numbers(
        cls,
        rule: UserNumberingRule,
        count: int = 10
    ) -> List[str]:
        """
        預覽連續多個編號（不消耗）

        Args:
            rule: 編號規則
            count: 產生數量

        Returns:
            List[str]: 預覽的編號列表
        """
        components = rule.get_components()
        period_key = cls._get_period_key(components)

        # 取得計數器（不鎖定）
        counter = cls._get_or_create_counter(rule, period_key, lock=False)

        # 模擬產生
        numbers = []
        state = {
            'prefix_index': counter.prefix_index,
            'suffix_index': counter.suffix_index,
            'current_seq': counter.current_seq
        }

        for _ in range(count):
            state = cls._calculate_next_state_from_dict(state, components)
            number = cls._compose_number(components, state)
            numbers.append(number)

        return numbers

    @classmethod
    def preview_from_config(
        cls,
        elements: dict,
        count: int = 10
    ) -> List[str]:
        """
        從配置預覽編號（用於設計器即時預覽）

        Args:
            elements: 編號元素配置
            count: 產生數量

        Returns:
            List[str]: 預覽的編號列表
        """
        components = elements.get('components', [])
        components = sorted(components, key=lambda x: x.get('order', 0))

        numbers = []
        state = {
            'prefix_index': 0,
            'suffix_index': 0,
            'current_seq': 0
        }

        for _ in range(count):
            state = cls._calculate_next_state_from_dict(state, components)
            number = cls._compose_number(components, state)
            numbers.append(number)

        return numbers

    @classmethod
    def validate_elements(cls, elements: dict) -> Tuple[bool, Optional[str]]:
        """
        驗證元素配置

        Args:
            elements: 編號元素配置

        Returns:
            Tuple[bool, str]: (是否有效, 錯誤訊息)
        """
        total_length = elements.get('total_length', 0)
        components = elements.get('components', [])

        if not components:
            return False, '至少需要一個編號元素'

        # 計算各元素長度
        calculated_length = 0
        has_sequence = False

        for comp in components:
            comp_type = comp.get('type')

            if comp_type == NumberingElementType.PREFIX:
                values = comp.get('values', [])
                if values:
                    calculated_length += max(len(v) for v in values)

            elif comp_type == NumberingElementType.SUFFIX:
                values = comp.get('values', [])
                if values:
                    calculated_length += max(len(v) for v in values)

            elif comp_type == NumberingElementType.SEQUENCE:
                has_sequence = True
                digits = comp.get('digits', 4)
                calculated_length += digits

            elif comp_type == NumberingElementType.YEAR:
                fmt = comp.get('format', 'yyyy')
                if fmt == 'yyyy':
                    calculated_length += 4
                elif fmt == 'yy':
                    calculated_length += 2
                elif fmt == 'y':
                    calculated_length += 1

            elif comp_type == NumberingElementType.YEAR_OFFSET:
                fmt = comp.get('format', 'fff')
                calculated_length += len(fmt)

            elif comp_type == NumberingElementType.MONTH:
                fmt = comp.get('format', 'mm')
                calculated_length += len(fmt)

        if not has_sequence:
            return False, '必須包含序號元素'

        if total_length > 0 and calculated_length != total_length:
            return False, f'元素總長度 ({calculated_length}) 與設定長度 ({total_length}) 不符'

        return True, None

    @classmethod
    def is_number_available(cls, org_secure_code: str, number: str) -> bool:
        """檢查編號是否可用（未被使用）"""
        return not UsedUserNumber.is_number_used(org_secure_code, number)

    @classmethod
    def sync_counter_to_used(cls, rule: UserNumberingRule) -> None:
        """
        同步 counter 到最新已使用的狀態。
        從 counter 當前位置開始向前推進，直到下一個編號可用為止。
        確保 get_next_number(consume=False) 直接回傳正確的下一個編號。
        """
        components = rule.get_components()
        period_key = cls._get_period_key(components)
        counter = cls._get_or_create_counter(rule, period_key, lock=True)
        max_attempts = cls._calculate_max_numbers(components)

        current_state = {
            'prefix_index': counter.prefix_index,
            'suffix_index': counter.suffix_index,
            'current_seq': counter.current_seq
        }

        # 持續推進直到下一個編號可用
        for _ in range(max_attempts):
            next_state = cls._calculate_next_state_from_dict(current_state, components)
            number = cls._compose_number(components, next_state)
            if cls.is_number_available(rule.org_secure_code, number):
                # 停在「前一個」狀態，讓 get_next_number 回傳這個可用編號
                counter.prefix_index = current_state['prefix_index']
                counter.suffix_index = current_state['suffix_index']
                counter.current_seq = current_state['current_seq']
                counter.updated_at = datetime.utcnow()
                return
            current_state = next_state

    @classmethod
    def _get_period_key(cls, components: List[dict]) -> str:
        """根據元素配置判斷週期 key"""
        for comp in components:
            if comp.get('type') == NumberingElementType.SEQUENCE:
                reset = comp.get('reset_period', NumberingResetPeriod.NEVER)
                now = datetime.now()
                if reset == NumberingResetPeriod.YEARLY:
                    return str(now.year)
                elif reset == NumberingResetPeriod.MONTHLY:
                    return f"{now.year}-{now.month:02d}"
        return 'all'

    @classmethod
    def _get_or_create_counter(
        cls,
        rule: UserNumberingRule,
        period_key: str,
        lock: bool = False
    ) -> UserNumberingCounter:
        """取得或建立計數器"""
        query = UserNumberingCounter.query.filter_by(
            org_secure_code=rule.org_secure_code,
            rule_secure_code=rule.secure_code,
            period_key=period_key
        )

        if lock:
            # 使用 FOR UPDATE 鎖定
            query = query.with_for_update()

        counter = query.first()

        if counter is None:
            # 建立新計數器
            counter = UserNumberingCounter(
                org_secure_code=rule.org_secure_code,
                rule_secure_code=rule.secure_code,
                period_key=period_key,
                prefix_index=0,
                suffix_index=0,
                current_seq=0
            )
            db.session.add(counter)
            if lock:
                db.session.flush()  # 確保獲得 ID

        return counter

    @classmethod
    def _calculate_next_state(
        cls,
        counter: UserNumberingCounter,
        components: List[dict]
    ) -> dict:
        """計算下一個計數器狀態"""
        return cls._calculate_next_state_from_dict({
            'prefix_index': counter.prefix_index,
            'suffix_index': counter.suffix_index,
            'current_seq': counter.current_seq
        }, components)

    @classmethod
    def _calculate_next_state_from_dict(
        cls,
        state: dict,
        components: List[dict]
    ) -> dict:
        """從字典狀態計算下一個狀態"""
        # 找出各配置
        seq_config = None
        prefix_config = None
        suffix_config = None

        for comp in components:
            if comp.get('type') == NumberingElementType.SEQUENCE:
                seq_config = comp
            elif comp.get('type') == NumberingElementType.PREFIX:
                prefix_config = comp
            elif comp.get('type') == NumberingElementType.SUFFIX:
                suffix_config = comp

        if seq_config is None:
            return state

        # 取得配置值
        digits = seq_config.get('digits', 4)
        start = seq_config.get('start', 1)
        max_seq = 10 ** digits - 1

        prefix_values = prefix_config.get('values', []) if prefix_config else []
        suffix_values = suffix_config.get('values', []) if suffix_config else []

        # 複製狀態
        new_state = state.copy()

        # 遞增序號（如果小於起始值則跳到起始值）
        if new_state['current_seq'] < start:
            new_state['current_seq'] = start
        else:
            new_state['current_seq'] += 1

        # 處理進位
        if new_state['current_seq'] > max_seq:
            new_state['current_seq'] = start

            if prefix_values:
                new_state['prefix_index'] += 1

                if new_state['prefix_index'] >= len(prefix_values):
                    new_state['prefix_index'] = 0

                    # 前綴循環完，後綴進位
                    if suffix_values:
                        new_state['suffix_index'] += 1
                        if new_state['suffix_index'] >= len(suffix_values):
                            new_state['suffix_index'] = 0

        return new_state

    @classmethod
    def _compose_number(cls, components: List[dict], state: dict) -> str:
        """組合編號字串"""
        parts = []
        now = datetime.now()

        for comp in sorted(components, key=lambda x: x.get('order', 0)):
            comp_type = comp.get('type')

            if comp_type == NumberingElementType.PREFIX:
                values = comp.get('values', [])
                if values:
                    idx = state.get('prefix_index', 0) % len(values)
                    parts.append(values[idx])

            elif comp_type == NumberingElementType.SUFFIX:
                values = comp.get('values', [])
                if values:
                    idx = state.get('suffix_index', 0) % len(values)
                    parts.append(values[idx])

            elif comp_type == NumberingElementType.SEQUENCE:
                digits = comp.get('digits', 4)
                seq = state.get('current_seq', 1)
                parts.append(str(seq).zfill(digits))

            elif comp_type == NumberingElementType.YEAR:
                fmt = comp.get('format', 'yyyy')
                if fmt == 'yyyy':
                    parts.append(str(now.year))
                elif fmt == 'yy':
                    parts.append(str(now.year % 100).zfill(2))
                elif fmt == 'y':
                    parts.append(str(now.year % 10))

            elif comp_type == NumberingElementType.YEAR_OFFSET:
                # 公式: |公元年 + 運算值| 補0至指定位數
                # 例如: offset=-1911, 2026+(-1911)=115, 取絕對值後補0
                offset = comp.get('offset', 0)
                fmt = comp.get('format', 'fff')
                year_val = abs(now.year + offset)
                if fmt == 'ffff':
                    parts.append(str(year_val).zfill(4))
                elif fmt == 'fff':
                    parts.append(str(year_val).zfill(3))
                elif fmt == 'ff':
                    parts.append(str(year_val).zfill(2))
                elif fmt == 'f':
                    parts.append(str(year_val).zfill(1))

            elif comp_type == NumberingElementType.MONTH:
                fmt = comp.get('format', 'mm')
                if fmt == 'mm':
                    parts.append(str(now.month).zfill(2))
                elif fmt == 'm':
                    parts.append(str(now.month))

        return ''.join(parts)

    @classmethod
    def get_default_rule(cls, org_secure_code: str, default_for: str = 'EMPLOYEE') -> Optional[UserNumberingRule]:
        """
        取得企業的預設編號規則

        Args:
            org_secure_code: 企業識別碼
            default_for: 預設用途 ('EMPLOYEE' 或 'EXTERNAL')

        Returns:
            UserNumberingRule 或 None
        """
        return UserNumberingRule.query.filter_by(
            org_secure_code=org_secure_code,
            default_for=default_for,
            is_active=True,
            is_deleted=False
        ).first()

    @classmethod
    def get_active_rules(cls, org_secure_code: str) -> List[UserNumberingRule]:
        """取得企業所有啟用的編號規則"""
        return UserNumberingRule.query.filter_by(
            org_secure_code=org_secure_code,
            is_active=True,
            is_deleted=False
        ).order_by(
            UserNumberingRule.default_for.desc().nullslast(),
            UserNumberingRule.name
        ).all()
