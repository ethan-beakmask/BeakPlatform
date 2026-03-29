"""
BeakPlatform 系統常數

集中定義系統級常數，避免分散在各模組中重複定義。
"""
import os

# 系統企業識別碼 (secure_code 和 domain_name 皆為此值)
# 必須在 .env 設定 SYSTEM_ORG_CODE，未設定則啟動失敗
SYSTEM_ORG_CODE = os.environ.get('SYSTEM_ORG_CODE')
if not SYSTEM_ORG_CODE:
    raise RuntimeError("環境變數 SYSTEM_ORG_CODE 未設定，請檢查 .env 檔案")
