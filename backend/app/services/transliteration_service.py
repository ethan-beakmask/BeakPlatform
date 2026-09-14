"""
Transliteration Service
亞洲語系自動拼音轉換服務

支援：
- 中文 → 拼音 (pypinyin)
- 日文 → 羅馬字 (pykakasi)
- 韓文 → 羅馬字 (基礎轉換)
- 自動偵測語系
"""
import re
import unicodedata
from typing import Tuple, Optional


class TransliterationService:
    """亞洲語系拼音轉換服務"""

    # 語言代碼
    LANG_CHINESE = 'zh'
    LANG_JAPANESE = 'ja'
    LANG_KOREAN = 'ko'
    LANG_UNKNOWN = 'unknown'
    LANG_MIXED = 'mixed'

    # Unicode 範圍
    CJK_UNIFIED = (0x4E00, 0x9FFF)  # CJK 統一漢字
    CJK_EXT_A = (0x3400, 0x4DBF)    # CJK 擴展 A
    HIRAGANA = (0x3040, 0x309F)     # 平假名
    KATAKANA = (0x30A0, 0x30FF)     # 片假名
    HANGUL = (0xAC00, 0xD7AF)       # 韓文音節
    HANGUL_JAMO = (0x1100, 0x11FF)  # 韓文字母

    _kakasi = None

    @classmethod
    def _get_kakasi(cls):
        """延遲載入 pykakasi"""
        if cls._kakasi is None:
            try:
                import pykakasi
                cls._kakasi = pykakasi.kakasi()
            except ImportError:
                cls._kakasi = False
        return cls._kakasi if cls._kakasi else None

    @classmethod
    def detect_language(cls, text: str) -> str:
        """
        偵測文字的主要語系

        Args:
            text: 輸入文字

        Returns:
            語言代碼: zh (中文), ja (日文), ko (韓文), unknown, mixed
        """
        if not text:
            return cls.LANG_UNKNOWN

        # 統計各語系字元數
        chinese_count = 0
        japanese_count = 0  # 假名
        korean_count = 0
        total_cjk = 0

        for char in text:
            code = ord(char)

            # 日文假名（平假名或片假名）
            if (cls.HIRAGANA[0] <= code <= cls.HIRAGANA[1] or
                cls.KATAKANA[0] <= code <= cls.KATAKANA[1]):
                japanese_count += 1
                continue

            # 韓文
            if (cls.HANGUL[0] <= code <= cls.HANGUL[1] or
                cls.HANGUL_JAMO[0] <= code <= cls.HANGUL_JAMO[1]):
                korean_count += 1
                continue

            # CJK 漢字（中日韓共用）
            if (cls.CJK_UNIFIED[0] <= code <= cls.CJK_UNIFIED[1] or
                cls.CJK_EXT_A[0] <= code <= cls.CJK_EXT_A[1]):
                total_cjk += 1
                continue

        # 判斷主要語系
        # 如果有假名，視為日文
        if japanese_count > 0:
            return cls.LANG_JAPANESE

        # 如果有韓文，視為韓文
        if korean_count > 0:
            return cls.LANG_KOREAN

        # 如果只有漢字，視為中文
        if total_cjk > 0:
            return cls.LANG_CHINESE

        return cls.LANG_UNKNOWN

    @classmethod
    def chinese_to_pinyin(cls, text: str, capitalize: bool = True) -> str:
        """
        中文轉拼音

        Args:
            text: 中文文字
            capitalize: 是否首字母大寫（人名格式）

        Returns:
            拼音字串
        """
        try:
            from pypinyin import pinyin, Style

            # 取得拼音（不含聲調）
            result = pinyin(text, style=Style.NORMAL, heteronym=False)

            if capitalize:
                # 人名格式：每個字首字母大寫
                parts = [p[0].capitalize() for p in result if p[0]]
                return ' '.join(parts)
            else:
                return ''.join([p[0] for p in result if p[0]])

        except ImportError:
            return text

    @classmethod
    def japanese_to_romaji(cls, text: str, capitalize: bool = True) -> str:
        """
        日文轉羅馬字

        Args:
            text: 日文文字
            capitalize: 是否首字母大寫

        Returns:
            羅馬字字串
        """
        kakasi = cls._get_kakasi()
        if not kakasi:
            return text

        try:
            result = kakasi.convert(text)
            romaji_parts = [item['hepburn'] for item in result]
            romaji = ''.join(romaji_parts)

            if capitalize:
                # 首字母大寫
                return romaji.title()
            return romaji

        except Exception:
            return text

    @classmethod
    def korean_to_romaji(cls, text: str, capitalize: bool = True) -> str:
        """
        韓文轉羅馬字（基礎版本）

        使用標準 Revised Romanization 規則的簡化版本。
        完整支援需要額外的韓文羅馬字庫。

        Args:
            text: 韓文文字
            capitalize: 是否首字母大寫

        Returns:
            羅馬字字串
        """
        # 韓文羅馬字轉換表（基礎）
        # 完整實作需要分解韓文音節為初聲、中聲、終聲
        # 這裡提供簡化版本，建議後續整合專門的韓文羅馬字庫

        result = []
        for char in text:
            code = ord(char)
            if cls.HANGUL[0] <= code <= cls.HANGUL[1]:
                # 基礎轉換：保留原字元（需要專門庫處理）
                result.append(char)
            else:
                result.append(char)

        # 如果沒有轉換（需要專門庫），返回原文
        output = ''.join(result)
        if output == text:
            # 嘗試使用 unicodedata 取得名稱
            try:
                names = []
                for char in text:
                    name = unicodedata.name(char, '')
                    if 'HANGUL' in name:
                        # 從 Unicode 名稱提取羅馬字（簡化）
                        # 例如: HANGUL SYLLABLE GA -> GA
                        parts = name.split()
                        if len(parts) >= 3:
                            names.append(parts[-1].lower())
                if names:
                    output = ' '.join(names)
                    if capitalize:
                        output = output.title()
                    return output
            except Exception:
                pass

        return text

    @classmethod
    def transliterate(cls, text: str, source_lang: str = None,
                      capitalize: bool = True) -> Tuple[str, str]:
        """
        自動轉換為羅馬字/拼音

        Args:
            text: 輸入文字
            source_lang: 來源語言（可選，自動偵測）
            capitalize: 是否首字母大寫

        Returns:
            Tuple[轉換結果, 偵測到的語言]
        """
        if not text or not text.strip():
            return ('', cls.LANG_UNKNOWN)

        text = text.strip()

        # 偵測語言
        lang = source_lang or cls.detect_language(text)

        # 根據語言進行轉換
        if lang == cls.LANG_CHINESE:
            result = cls.chinese_to_pinyin(text, capitalize)
        elif lang == cls.LANG_JAPANESE:
            result = cls.japanese_to_romaji(text, capitalize)
        elif lang == cls.LANG_KOREAN:
            result = cls.korean_to_romaji(text, capitalize)
        else:
            # 未知語言，返回原文
            result = text

        return (result, lang)

    @classmethod
    def transliterate_name(cls, name: str) -> dict:
        """
        轉換人名（專用方法）

        自動偵測語言並轉換為適合人名的格式。

        Args:
            name: 人名

        Returns:
            {
                'original': 原始輸入,
                'romanized': 羅馬字/拼音,
                'language': 偵測到的語言,
                'confidence': 信心度 (high/medium/low)
            }
        """
        if not name or not name.strip():
            return {
                'original': name or '',
                'romanized': '',
                'language': cls.LANG_UNKNOWN,
                'confidence': 'low'
            }

        name = name.strip()
        lang = cls.detect_language(name)
        romanized, _ = cls.transliterate(name, lang, capitalize=True)

        # 判斷信心度
        if lang in (cls.LANG_CHINESE, cls.LANG_JAPANESE):
            confidence = 'high'
        elif lang == cls.LANG_KOREAN:
            confidence = 'medium'  # 韓文轉換較不完整
        else:
            confidence = 'low'

        return {
            'original': name,
            'romanized': romanized,
            'language': lang,
            'confidence': confidence
        }
