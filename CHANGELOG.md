# Changelog

本專案的所有重要變更都會記錄在此檔案中。

格式基於 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)。

## [Unreleased]

### Added
- 表單設計器左側面板新增「表單標題」元件（HTML Element h3 置中），拖入即用
- 新建表單模板/流程連帶表單自動帶入標題元件，content 為表單名稱
- 新增表單與新增流程的預設分類改為「流程記錄」
- 表單填寫端載入 `formio-theme.css`，實現與設計器 WYSIWYG 視覺同步
- 填寫/簽核/閱讀 Modal 灰色畫布背景 + 白色表單區域 + 陰影（匹配設計器 preview）

### Changed
- 前端 HTML 瘦身 Phase 0-3：大型模板抽離內嵌 JS/CSS 為獨立靜態檔，符合 FRONT-01/02 規範
  - Phase 0: 建立 `common.css` 共用樣式、關閉 Bulma Issue #11
  - Phase 1: `template_list.html` (700→244)、`workflow_list.html` (674→296)
  - Phase 2: `holidays.html` (1011→205)、`schedules.html` (905→226)、`form_center.html` (1880→393)、`form_designer.html` (479+1459→133)
  - Phase 3: `groups.html` (1305→238)、`users/create.html` (930→256)、`departments.html` CSS partial→靜態檔
  - Phase 4: 8 個模板抽離 — `users/edit.html` (600→361)、`mappings_list.html` (623→276)、`quick_login.html` (709→215)、`settings.html` (640→319)、`users/view.html` (497→220)、`numbering/edit.html` (451→290)、`org-admins/list.html` (391→162)、`category_list.html` (379→164)
  - Phase 5: 全模板合規審計完成，CSS 去重（移除 app.css / user-form.css 中 common.css 重複定義）
  - Phase 6: `organizations/list.html` (1004→309)、`workflow_designer.html` (1081→845，獨立頁面)
  - Phase 7: `menu.html` (406→45)、`hostconfig/index.html` (295→111)
  - Phase 8: CSS 去重 — 模態框/密碼重設/password-field/form-hint/alert/help-text 抽至 `common.css`，6 個 CSS 檔移除重複
- 部門/社群頁面共用 `org-tree.css` (467 行)，消除 CSS 重複
- CLAUDE.md FRONT-01 新增 JS 抽離三種模式說明 (A: 直接搬移 / B: Window Bridge / C: 保留 Partial)
- 表單設計器工具列「表單檔名」欄位寬度 180→210px、「分類」欄位寬度 140→170px
- 工作流列表新增「專屬」「通用」子流程數量欄位，API 批次計算
- 流程設計器描述欄位改為多行編輯 Modal，支援換行儲存
- 新建流程自動適應視圖，預設 Start/End 節點進入視野
- CSS 框架統一為 Bootstrap 5.3.2，移除 Bulma（`form_center.html`、`workflow_list.html`、`workflow_designer.html`）
- 刪除 `bulma.min.css`，消除 Bulma 與 Bootstrap/Form.io 的 CSS 衝突（heading 大小、columns 佈局、input 樣式）
- 工作流列表頁 Bulma → Bootstrap 改寫（表格、按鈕、標籤、Tab、Modal）
- 表單中心主旨欄位超長文字自動截斷顯示 `...`（純視覺，不影響資料）
- 刪除主流程時遞迴軟刪除所有專屬子流程及相關配對，通用子流程保留
- 刪除前檢查運行中實例，有則阻擋刪除
- SubFlow 子流程功能：引擎核心支援子流程呼叫
- 流程樹系圖獨立分頁 (`/forms/workflows/<id>/tree`)，橫向佈局含原尺寸縮圖
- 單一流程樹 API (`GET /api/form-workflow/workflows/flow-trees/<secure_code>`)
- SubFlow 節點建立/選擇子流程後自動套用並重整流程樹系
- 儲存並關閉依來源返回：從樹系圖來的回樹系圖，從清單來的回清單
- 流程監控模態框標題列顯示五欄版本資訊（發行版本、表單名稱、表單版本、流程名稱、流程版本）
- 強制結束流程功能（發起人/企業管理員可在監控畫面強制取消 RUNNING 流程）
- 歷史列表納入 CANCELLED 和 REJECTED 狀態的表單
- Docker 化 CI/CD 部署環境 (PostgreSQL 16 + Redis 7 + Gunicorn + Nginx)
- CI 通過後自動部署到 staging 環境 (192.168.0.15:8000)
- CI/CD 環境建置文件 (`docs/CICD_SETUP.md`)
- 群組功能優化：空群組修正、自訂顏色、管理面板重構
- 流程設計器所需的企業資料查詢 API
- 配對列表顯示發行版本資訊（運作版本、發行名稱、快照名稱）
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
- 流程設計器上方工具列改為白底扁平風格（移除漸層背景），按鈕色值對齊 Bootstrap 色系
- 流程設計器版本字體放大（11px → 14px），描述欄改為 readonly 預覽第一行
- 工作流列表移除「類型」「節點數」欄位，預設顯示模式改為清單
- 工作流列表描述欄只顯示第一行，超過 500px 自動截斷
- 縮圖生成移除多餘的 `cy.fit()`，使用 `full: true` 直接導出避免改變畫布比例
- 表單中心欄寬統一：單號 140px、表單 145px、類別 85px、發起人 90px、時間類欄位 150px
- 表單中心字體統一：內文 13px、標題/表單名稱 14px bold
- 待簽核表格欄位順序調整（單號→表單→主旨→發起人→類別→目前關卡→等待時間→操作）
- 新增工作流對話框「設為子流程」改為「設為通用子流程」，移除多餘說明文字
- 新增表單模板按鈕與對話框文字修正
- 表單/工作流對話框 checkbox 排版修正（靠左對齊）
- 流程縮圖改為單一 600×400 (3:2 橫式)，移除 1x1/1x2 兩種尺寸節省算力
- 流程縮圖生成加入 24px 白邊，cy.fit padding 縮小讓節點更大
- 表單縮圖改為 600×900 (2:3 直式)，viewport 800×800 確保並排欄位正確渲染
- 表單縮圖生成加入 PIL 自動裁切空白
- 流程列表頁/表單列表頁容器寬度從 1200px 加大至 1800px
- 流程縮圖 grid 改為 5 欄，框以 aspect-ratio 3:2 自適應
- 表單縮圖 grid 改為 8 欄，框以 aspect-ratio 2:3 自適應
- 流程樹系圖節點放大至 240×195，縮圖區 224×150
- 表單列表頁分類篩選移除「全部」chip，預設選第一個分類，無分類歸入「其他」
- 表單中心左側分類移除「全部」，預設選第一個父分類，無分類歸入「其他」
- 表單中心子分類頁籤移除「全部」，追加「其他」收納未歸子分類的表單，預設選第一個
- 工作流列表頁 Tab 精簡為「主流程」與「通用子流程」，移除全部 Tab
- 專屬子流程從列表頁隱藏，改為透過主流程的樹系圖查看
- 分類篩選移除「全部」chip，預設選第一個分類，無分類歸入「其他」
- 列表 badge 三態顯示：主流程 / 通用子流程 / 專屬子流程
- API `flow_type=subflow` 改為只回傳通用子流程（排除專屬）
- restart_flask.sh 改為確認 executor/emailrelay 服務運行，移除舊的 disable 邏輯
- ProductionConfig SESSION_REDIS 改用 redis.from_url() 建立連線物件
- CI workflow 升級為 CI/CD pipeline
- E-MailRelay 從系統安裝改為自包含安裝 /opt/E-MailRelay
- 表單設計器與流程設計器 navbar 改為共用風格
- HTML 模板瘦身：4 個大檔拆為 Jinja2 partial
- Node Type 定義改為 DB 驅動，消除 API 硬編碼
- 表單中心瘦身與全專案 port/命名修正
- 代碼內品牌引用恢復為 BeakMask

### Fixed
- 描述編輯 Modal 儲存後換行遺失（input type=text 會吃換行，改用 currentWorkflow 物件直接存取）
- 儲存流程時縮圖生成觸發 cy.fit() 導致畫布比例跳掉
- 專屬子流程被歸類為通用的 bug（to_dict 補回 parent_workflow_secure_code）
- 分類 chip 重複「其他」問題（DB 已有時不再追加）
- 工作流引擎統一使用發行快照 (graph_snapshot) 而非設計圖，避免版本間節點 ID 不匹配導致流程中斷
- CD deploy 改用直接 SSH 取代 appleboy/ssh-action (data.forgejo.org 無此 mirror)
- Docker entrypoint 表名檢查錯誤 (`user` → `organizations`)，導致重複建立 system.local
- Docker 部署缺少平台級選單初始化 (init_menus.py)
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
