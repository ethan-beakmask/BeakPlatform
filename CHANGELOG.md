# Changelog

本專案的所有重要變更都會記錄在此檔案中。

格式基於 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)。

## [Unreleased]

### Added
- Docker 化 CI/CD 部署環境 (PostgreSQL 16 + Redis 7 + Gunicorn + Nginx)
- CI 通過後自動部署到 staging 環境 (192.168.0.15:8000)
- CI/CD 環境建置文件 (`docs/CICD_SETUP.md`)
- 群組功能優化：空群組修正、自訂顏色、管理面板重構
- 流程設計器所需的企業資料查詢 API
- 列表多選批次操作與配對資訊顯示
- Ctrl+Z Undo 系統，替換節點改為記憶體保留
- 流程設計器快捷鍵與畫布改善
- End 節點三種結束模式 (detach/cancel/strict)
- 表單中心序號 TEST/PROC 標記補齊與獨立清單頁面
- 分類結構改為靈活一/二層（不強制子分類）
- 表單流程分類改為二層結構 (parent/child)
- 帳號管理重構與 Navbar 個人化顯示
- i18n 系統全面建置 (Flask-Babel 整合)
- 選單多語系、企業語系/時區設定、個人時區
- CI/CD 安全檢查 (Semgrep + Bandit)
- E-MailRelay 通知節點 handler
- 模組靜態檔案機制
- 表單閱讀功能與統一底圖/寬度渲染
- 分類管理與底圖管理功能
- 表單流程模組完整移轉 (Step 3)
- 安裝文件與腳本 (Step 4)
- 模組化標準驗證 (Step 5)

### Changed
- ProductionConfig SESSION_REDIS 改用 redis.from_url() 建立連線物件
- CI workflow 升級為 CI/CD pipeline
- E-MailRelay 從系統安裝改為自包含安裝 /opt/E-MailRelay
- 表單設計器與流程設計器 navbar 改為共用風格
- HTML 模板瘦身：4 個大檔拆為 Jinja2 partial
- Node Type 定義改為 DB 驅動，消除 API 硬編碼
- 表單中心瘦身與全專案 port/命名修正
- 代碼內品牌引用恢復為 BeakMask

### Fixed
- 修復工作流節點重複執行的 race condition
- 修復 VariableService 並行寫入變數的 race condition
- 儲存流程前自動套用當前面板設定，避免 config 遺失
- E-MailRelay 服務名稱修正與流程設計器線條屬性儲存
- 通知節點 handler 群組解析修正
- 流程首次儲存自動建立表單時觸發背景縮圖生成
- 節點邊框隱藏時 Shift 連線高亮不顯示
- End 節點依結束模式變色失效修正
- Node Type 命名正規化 (方案 C Phase 1-4)
- 分類預設值修正、移除未分類選項
- 分類管理頁面空白修正
- 表單中心時區換算與 ResourceGateway 多欄位排序

## [0.2.0-pre-a6] - 2025-12-26

### Added
- Step 2 完成：權限接口、選單整合、CLI 命令
- 模組化基礎架構建立
- 用戶密碼欄位高強度密碼產生器

### Fixed
- 用戶重設密碼對話框開啟時自動產生密碼
- 企業管理員設定頁面調整

## [0.1.0] - 2025-12-20

- 初始版本：多租戶權限管理平台基礎架構
