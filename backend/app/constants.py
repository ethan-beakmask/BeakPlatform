"""
BeakPlatform 系統常數

集中定義系統級常數，避免分散在各模組中重複定義。
"""
import os

# 系統企業識別碼 (secure_code 和 domain_name 皆為此值)
# 部署時由 .env 的 SYSTEM_ORG_CODE 決定，開發環境預設 'system.local'
SYSTEM_ORG_CODE = os.environ.get('SYSTEM_ORG_CODE', 'system.local')
