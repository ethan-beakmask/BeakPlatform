BeakMask Scripts 工具說明
==========================

1. analyze_project.py - 專案分析工具
   用途：整合多種分析功能，產生 Excel/JSON 報告
   用法：
     python scripts/analyze_project.py routes      # API 路由分析
     python scripts/analyze_project.py structure   # 目錄結構分析
     python scripts/analyze_project.py database    # 資料庫結構匯出
     python scripts/analyze_project.py unused      # 未使用檔案分析
     python scripts/analyze_project.py all         # 執行所有分析
   依賴：pip install openpyxl psycopg2-binary

2. spec_check.py - 規格檢查工具
   用途：檢查程式碼是否符合 BeakMask 安全規範
   用法：python scripts/spec_check.py .
   檢查項目：
     - AUTH-01: 全域認證攔截
     - AUTH-02: 統一認證 Decorator
     - TENANT-01: 強制企業隔離
     - TENANT-02: ResourceGateway 要求

3. security_scan.sh - 安全掃描工具
   用途：使用 Semgrep 掃描安全漏洞
   用法：
     ./scripts/security_scan.sh           # Flask 專用規則
     ./scripts/security_scan.sh --full    # 全部規則
   依賴：需安裝 semgrep

4. seed_data.py - 測試資料生成
   用途：產生開發環境測試資料
   用法：python scripts/seed_data.py
   注意：僅用於開發環境

最後更新：2025-12-22
