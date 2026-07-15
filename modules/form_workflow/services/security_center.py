"""
資安案件分類隔離常數（原子 4845 / handoff_security_case_center.md）

資安類表單以 fw_categories 分類隔離：分類 secure_code 一律以
SECURITY_CATEGORY_PREFIX 開頭（seed: CAT_SECURITY_f5bc0629「資安案件」）。
一般表單中心（/forms/center）過濾掉此前綴的表單；
資安案件處置中心（/open-defense/security-cases）只顯示此前綴的案件。

引擎與資料表完全共用，只有 UI 層分開（用戶明確要求，不 clone 引擎）。
"""

SECURITY_CATEGORY_PREFIX = 'CAT_SECURITY_'


def is_security_category(category_secure_code) -> bool:
    """判斷分類 secure_code 是否屬資安案件分類。None 視為一般分類。"""
    return bool(category_secure_code and
                str(category_secure_code).startswith(SECURITY_CATEGORY_PREFIX))
