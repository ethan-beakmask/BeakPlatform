"""
BeakPlatform Code Generator Service
自動代碼產生服務

功能：
- 將用戶輸入的名稱自動轉換為符合格式的代碼
- 支援多語言（中/日/英，可擴展）
- 代碼驗證與衝突檢查
- 通用化設計：可用於部門、職稱、角色等

架構：
- CodeGenerator：主服務類別
- LanguageProcessor：語言處理器基底類別
- ChineseProcessor、JapaneseProcessor、LatinProcessor：具體處理器
- UnidecodeProcessor：Fallback 處理器
"""
import re
import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Callable, Type, Dict, Any

# 語言偵測
try:
    from langdetect import detect, DetectorFactory
    # 固定隨機種子，確保結果一致
    DetectorFactory.seed = 0
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False

# 中文拼音
try:
    from pypinyin import pinyin, Style
    PYPINYIN_AVAILABLE = True
except ImportError:
    PYPINYIN_AVAILABLE = False

# 日文羅馬字
try:
    import pykakasi
    PYKAKASI_AVAILABLE = True
except ImportError:
    PYKAKASI_AVAILABLE = False

# 通用 Unicode 轉 ASCII
try:
    from unidecode import unidecode
    UNIDECODE_AVAILABLE = True
except ImportError:
    UNIDECODE_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# 常數定義
# =============================================================================

# 代碼格式正則：大寫英文、數字、底線，開頭必須是英文
CODE_PATTERN = re.compile(r'^[A-Z][A-Z0-9_]*$')

# 代碼最大長度
MAX_CODE_LENGTH = 50

# 保留字（系統關鍵字，不可作為代碼）
RESERVED_CODES = frozenset({
    'SYSTEM', 'ADMIN', 'ROOT', 'NULL', 'UNDEFINED', 'NONE',
    'TRUE', 'FALSE', 'TEST', 'TEMP', 'TMP', 'DEFAULT',
    'ALL', 'ANY', 'NEW', 'DELETE', 'UPDATE', 'INSERT', 'SELECT',
})

# 常用詞彙對照表（中文 → 英文），提升翻譯品質
COMMON_TERMS_ZH = {
    # 職位相關
    '經理': 'MANAGER',
    '副經理': 'DEPUTY_MANAGER',
    '助理': 'ASSISTANT',
    '主管': 'SUPERVISOR',
    '副主管': 'DEPUTY_SUPERVISOR',
    '主任': 'DIRECTOR',
    '副主任': 'DEPUTY_DIRECTOR',
    '組長': 'TEAM_LEADER',
    '副組長': 'DEPUTY_TEAM_LEADER',
    '專員': 'SPECIALIST',
    '工程師': 'ENGINEER',
    '資深': 'SENIOR',
    '初級': 'JUNIOR',
    '實習': 'INTERN',
    '顧問': 'CONSULTANT',
    '總監': 'GENERAL_DIRECTOR',
    '執行長': 'CEO',
    '技術長': 'CTO',
    '財務長': 'CFO',
    '營運長': 'COO',
    '董事長': 'CHAIRMAN',
    '總經理': 'GENERAL_MANAGER',
    '副總經理': 'DEPUTY_GM',
    '處長': 'DIVISION_HEAD',
    '副處長': 'DEPUTY_DIVISION_HEAD',
    '課長': 'SECTION_CHIEF',
    '副課長': 'DEPUTY_SECTION_CHIEF',
    '股長': 'UNIT_CHIEF',
    '秘書': 'SECRETARY',
    '會計': 'ACCOUNTANT',
    '出納': 'CASHIER',
    '採購': 'PROCUREMENT',
    '倉管': 'WAREHOUSE',

    # 部門相關
    '部': 'DEPT',
    '處': 'DIVISION',
    '室': 'OFFICE',
    '組': 'TEAM',
    '課': 'SECTION',
    '股': 'UNIT',
    '中心': 'CENTER',
    '總部': 'HQ',
    '分公司': 'BRANCH',
    '人資': 'HR',
    '人事': 'HR',
    '人力資源': 'HR',
    '財務': 'FINANCE',
    '會計': 'ACCOUNTING',
    '業務': 'SALES',
    '行銷': 'MARKETING',
    '研發': 'RD',
    '資訊': 'IT',
    '資訊技術': 'IT',
    '行政': 'ADMIN',
    '總務': 'GENERAL_AFFAIRS',
    '法務': 'LEGAL',
    '稽核': 'AUDIT',
    '品管': 'QC',
    '品質': 'QUALITY',
    '生產': 'PRODUCTION',
    '製造': 'MANUFACTURING',
    '物流': 'LOGISTICS',
    '客服': 'CS',
    '客戶服務': 'CUSTOMER_SERVICE',
    '企劃': 'PLANNING',
    '策略': 'STRATEGY',
    '公關': 'PR',
    '設計': 'DESIGN',
    '工程': 'ENGINEERING',

    # 角色相關
    '管理員': 'ADMIN',
    '成員': 'MEMBER',
    '召集人': 'CONVENER',
    '代理人': 'PROXY',
    '員工': 'EMPLOYEE',
    '外部': 'EXTERNAL',
    '訪客': 'GUEST',
}

# 常用詞彙對照表（日文 → 英文）
COMMON_TERMS_JA = {
    # 職位相關
    '部長': 'DEPARTMENT_HEAD',
    '課長': 'SECTION_CHIEF',
    '係長': 'SUBSECTION_CHIEF',
    '主任': 'CHIEF',
    '社長': 'PRESIDENT',
    '副社長': 'VICE_PRESIDENT',
    '専務': 'EXECUTIVE_DIRECTOR',
    '常務': 'MANAGING_DIRECTOR',
    '取締役': 'DIRECTOR',
    '監査役': 'AUDITOR',
    '顧問': 'ADVISOR',
    '相談役': 'SENIOR_ADVISOR',
    '秘書': 'SECRETARY',
    'マネージャー': 'MANAGER',
    'リーダー': 'LEADER',
    'エンジニア': 'ENGINEER',
    'アシスタント': 'ASSISTANT',

    # 部門相關
    '営業部': 'SALES_DEPT',
    '人事部': 'HR_DEPT',
    '総務部': 'GENERAL_AFFAIRS_DEPT',
    '経理部': 'ACCOUNTING_DEPT',
    '技術部': 'ENGINEERING_DEPT',
    '開発部': 'DEVELOPMENT_DEPT',
    '企画部': 'PLANNING_DEPT',
}


# =============================================================================
# 語言處理器
# =============================================================================

class LanguageProcessor(ABC):
    """語言處理器基底類別"""

    @property
    @abstractmethod
    def language_code(self) -> str:
        """語言代碼（如 'zh', 'ja', 'en'）"""
        pass

    @property
    @abstractmethod
    def language_name(self) -> str:
        """語言名稱（如 '中文', '日本語', 'English'）"""
        pass

    @abstractmethod
    def can_process(self, text: str) -> bool:
        """判斷是否可以處理此文字"""
        pass

    @abstractmethod
    def to_latin(self, text: str) -> str:
        """將文字轉換為拉丁字母"""
        pass

    def get_common_term(self, text: str) -> Optional[str]:
        """從常用詞彙表查找對應英文"""
        return None


class ChineseProcessor(LanguageProcessor):
    """中文處理器（使用漢語拼音）"""

    @property
    def language_code(self) -> str:
        return 'zh'

    @property
    def language_name(self) -> str:
        return '中文'

    def can_process(self, text: str) -> bool:
        if not PYPINYIN_AVAILABLE:
            return False
        # 檢查是否包含中文字元
        return bool(re.search(r'[\u4e00-\u9fff]', text))

    def get_common_term(self, text: str) -> Optional[str]:
        return COMMON_TERMS_ZH.get(text)

    def to_latin(self, text: str) -> str:
        if not PYPINYIN_AVAILABLE:
            return text

        # 先查常用詞彙表
        common = self.get_common_term(text)
        if common:
            return common

        # 嘗試組合查詢（如「業務經理」→ SALES + MANAGER）
        result_parts = []
        remaining = text

        # 貪婪匹配：從長到短嘗試匹配詞彙表
        while remaining:
            matched = False
            for length in range(len(remaining), 0, -1):
                substr = remaining[:length]
                if substr in COMMON_TERMS_ZH:
                    result_parts.append(COMMON_TERMS_ZH[substr])
                    remaining = remaining[length:]
                    matched = True
                    break

            if not matched:
                # 無法匹配，用拼音轉換單個字元
                char = remaining[0]
                if re.match(r'[\u4e00-\u9fff]', char):
                    py = pinyin(char, style=Style.NORMAL)
                    result_parts.append(py[0][0].upper() if py else char)
                else:
                    result_parts.append(char.upper())
                remaining = remaining[1:]

        return '_'.join(result_parts) if result_parts else text


class JapaneseProcessor(LanguageProcessor):
    """日文處理器（使用 Hepburn 羅馬字）"""

    def __init__(self):
        self._kakasi = None

    @property
    def kakasi(self):
        if self._kakasi is None and PYKAKASI_AVAILABLE:
            self._kakasi = pykakasi.kakasi()
        return self._kakasi

    @property
    def language_code(self) -> str:
        return 'ja'

    @property
    def language_name(self) -> str:
        return '日本語'

    def can_process(self, text: str) -> bool:
        if not PYKAKASI_AVAILABLE:
            return False
        # 檢查是否包含日文字元（平假名、片假名）
        return bool(re.search(r'[\u3040-\u309f\u30a0-\u30ff]', text))

    def get_common_term(self, text: str) -> Optional[str]:
        return COMMON_TERMS_JA.get(text)

    def to_latin(self, text: str) -> str:
        if not self.kakasi:
            return text

        # 先查常用詞彙表
        common = self.get_common_term(text)
        if common:
            return common

        # 使用 pykakasi 轉換
        result = self.kakasi.convert(text)
        parts = [item['hepburn'].upper() for item in result if item['hepburn']]
        return '_'.join(parts) if parts else text


class LatinProcessor(LanguageProcessor):
    """拉丁語系處理器（英文等）"""

    @property
    def language_code(self) -> str:
        return 'en'

    @property
    def language_name(self) -> str:
        return 'English'

    def can_process(self, text: str) -> bool:
        # 純拉丁字母（包含重音符號）
        return bool(re.match(r'^[\x00-\x7f\u00c0-\u024f\s]+$', text))

    def to_latin(self, text: str) -> str:
        # 已經是拉丁字母，直接返回大寫
        return text.upper()


class UnidecodeProcessor(LanguageProcessor):
    """通用 Fallback 處理器（使用 Unidecode）"""

    @property
    def language_code(self) -> str:
        return 'und'  # Undetermined

    @property
    def language_name(self) -> str:
        return 'Universal'

    def can_process(self, text: str) -> bool:
        # 始終可以處理
        return UNIDECODE_AVAILABLE

    def to_latin(self, text: str) -> str:
        if not UNIDECODE_AVAILABLE:
            # 最後防線：移除非 ASCII 字元
            return re.sub(r'[^\x00-\x7f]', '', text).upper()
        return unidecode(text).upper()


# =============================================================================
# 主服務類別
# =============================================================================

class CodeGenerator:
    """
    自動代碼產生服務

    使用方式：
        generator = CodeGenerator()

        # 自動產生代碼
        code = generator.generate('業務經理')  # → 'SALES_MANAGER'

        # 驗證手動輸入的代碼
        is_valid, error = generator.validate('MY_CODE')

        # 檢查代碼是否重複（需提供檢查函數）
        def check_exists(code):
            return Role.query.filter_by(code=code).first() is not None

        code = generator.generate('業務經理', exists_checker=check_exists)
    """

    def __init__(self):
        # 註冊語言處理器（順序重要：優先使用專門處理器）
        self._processors: List[LanguageProcessor] = [
            ChineseProcessor(),
            JapaneseProcessor(),
            LatinProcessor(),
            UnidecodeProcessor(),  # Fallback
        ]

    @property
    def available_processors(self) -> List[Dict[str, str]]:
        """取得可用的語言處理器列表"""
        return [
            {
                'code': p.language_code,
                'name': p.language_name,
                'available': p.can_process('test')
            }
            for p in self._processors
        ]

    def detect_language(self, text: str) -> Optional[str]:
        """偵測文字語言"""
        if not LANGDETECT_AVAILABLE:
            return None
        try:
            return detect(text)
        except Exception:
            return None

    def _get_processor(self, text: str) -> LanguageProcessor:
        """根據文字內容選擇適合的處理器"""
        for processor in self._processors:
            if processor.can_process(text):
                return processor
        # 不應該到這裡，因為 UnidecodeProcessor 始終可用
        return self._processors[-1]

    def _format_code(self, raw: str) -> str:
        """格式化代碼：大寫、空格轉底線、移除特殊字元"""
        # 移除首尾空白
        code = raw.strip()

        # 轉大寫
        code = code.upper()

        # 空格和連字號轉底線
        code = re.sub(r'[\s\-]+', '_', code)

        # 移除非英文字母、數字、底線的字元
        code = re.sub(r'[^A-Z0-9_]', '', code)

        # 合併多個連續底線
        code = re.sub(r'_+', '_', code)

        # 移除首尾底線
        code = code.strip('_')

        # 確保開頭是字母（如果開頭是數字，加前綴）
        if code and code[0].isdigit():
            code = 'X_' + code

        # 長度限制
        if len(code) > MAX_CODE_LENGTH:
            code = code[:MAX_CODE_LENGTH].rstrip('_')

        return code

    def _add_suffix(self, base_code: str, suffix_num: int) -> str:
        """加上數字後綴"""
        suffix = f'_{suffix_num:02d}'
        max_base = MAX_CODE_LENGTH - len(suffix)
        if len(base_code) > max_base:
            base_code = base_code[:max_base].rstrip('_')
        return f'{base_code}{suffix}'

    def generate(
        self,
        name: str,
        exists_checker: Optional[Callable[[str], bool]] = None,
        max_attempts: int = 100
    ) -> str:
        """
        根據名稱自動產生代碼

        Args:
            name: 輸入名稱（如「業務經理」）
            exists_checker: 檢查代碼是否已存在的函數
            max_attempts: 最大嘗試次數（用於處理衝突）

        Returns:
            產生的代碼（如 'SALES_MANAGER'）

        Raises:
            ValueError: 無法產生有效代碼
        """
        if not name or not name.strip():
            raise ValueError('名稱不可為空')

        # 選擇處理器並轉換
        processor = self._get_processor(name)
        raw_code = processor.to_latin(name)

        # 格式化
        base_code = self._format_code(raw_code)

        if not base_code:
            # 如果格式化後為空，使用 fallback
            base_code = self._format_code(UnidecodeProcessor().to_latin(name))

        if not base_code:
            raise ValueError(f'無法從名稱 "{name}" 產生有效代碼')

        # 檢查保留字
        if base_code in RESERVED_CODES:
            base_code = f'{base_code}_CUSTOM'

        # 如果沒有提供檢查函數，直接返回
        if exists_checker is None:
            return base_code

        # 檢查衝突並加後綴
        code = base_code
        attempt = 0

        while exists_checker(code) and attempt < max_attempts:
            attempt += 1
            code = self._add_suffix(base_code, attempt)

        if attempt >= max_attempts:
            raise ValueError(f'代碼 "{base_code}" 衝突過多，無法產生唯一代碼')

        return code

    def validate(self, code: str) -> tuple[bool, Optional[str]]:
        """
        驗證代碼格式

        Args:
            code: 要驗證的代碼

        Returns:
            (is_valid, error_message)
        """
        if not code:
            return False, '代碼不可為空'

        if len(code) > MAX_CODE_LENGTH:
            return False, f'代碼長度不可超過 {MAX_CODE_LENGTH} 字元'

        if not CODE_PATTERN.match(code):
            return False, '代碼格式錯誤：只能包含大寫英文、數字和底線，且必須以英文開頭'

        if code in RESERVED_CODES:
            return False, f'"{code}" 是系統保留字，不可使用'

        return True, None

    def validate_with_exists_check(
        self,
        code: str,
        exists_checker: Callable[[str], bool]
    ) -> tuple[bool, Optional[str]]:
        """
        驗證代碼格式並檢查是否重複

        Args:
            code: 要驗證的代碼
            exists_checker: 檢查代碼是否已存在的函數

        Returns:
            (is_valid, error_message)
        """
        is_valid, error = self.validate(code)
        if not is_valid:
            return False, error

        if exists_checker(code):
            return False, f'代碼 "{code}" 已存在'

        return True, None

    def suggest(
        self,
        name: str,
        exists_checker: Optional[Callable[[str], bool]] = None,
        count: int = 3
    ) -> List[str]:
        """
        根據名稱建議多個可用代碼

        Args:
            name: 輸入名稱
            exists_checker: 檢查代碼是否已存在的函數
            count: 建議數量

        Returns:
            建議的代碼列表
        """
        suggestions = []

        try:
            # 第一個：自動產生的最佳代碼
            code = self.generate(name, exists_checker)
            suggestions.append(code)
        except ValueError:
            pass

        # 額外建議：加上常見後綴
        if suggestions:
            base = suggestions[0].rstrip('0123456789_')
            suffixes = ['01', '02', 'NEW', 'V2']

            for suffix in suffixes:
                if len(suggestions) >= count:
                    break

                candidate = f'{base}_{suffix}'
                is_valid, _ = self.validate(candidate)

                if is_valid:
                    if exists_checker is None or not exists_checker(candidate):
                        if candidate not in suggestions:
                            suggestions.append(candidate)

        return suggestions[:count]


# 單例實例
_code_generator: Optional[CodeGenerator] = None


def get_code_generator() -> CodeGenerator:
    """取得 CodeGenerator 單例"""
    global _code_generator
    if _code_generator is None:
        _code_generator = CodeGenerator()
    return _code_generator
