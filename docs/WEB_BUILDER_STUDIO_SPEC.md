# Web Builder Studio -- 統一設計器規格書

> 版本: 1.0 | 日期: 2026-03-05 | 狀態: 已核准

---

## 一、目標與定位

讓無碼開發用戶（企業管理員/文書人員）能：
1. 建立子系統開發案，自主開發資料庫讀寫的小系統（如訂餐系統）
2. 透過 Site Map 樹狀結構定義網站目錄/頁面層級
3. 在統一設計器中，點擊樹節點即切換頁面設計，佈置元件（DATALIST 等）
4. 開發完成後申請上線，出現在 menu 供用戶使用

**核心原則：權限控制是基礎，所有功能在權限架構上開發。**

---

## 二、子系統生命週期與狀態機

### 2.1 狀態定義

```
DRAFT (開發中) --> PUBLISHED (上線)
  ^                    |
  +--- 新版本開發 ------+
```

> PENDING_REVIEW / APPROVED 狀態留給 Phase 3 申請流程再加，Phase 1 先實作 DRAFT/PUBLISHED 兩態。

| 狀態 | menu 可見性 | 可見對象 | 設計器可用 |
|------|------------|---------|-----------|
| DRAFT | 不出現在 menu | 開發者名單（developers JSONB） | 是 |
| PUBLISHED | 出現在 menu | 依角色控制（現有機制） | 是（改版） |

### 2.2 DB 變更 -- dc_sub_systems 表擴充

新增欄位（Migration 006）：

```sql
ALTER TABLE dc_sub_systems
  ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'draft',
  ADD COLUMN IF NOT EXISTS developers JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS layout_mode VARCHAR(20) NOT NULL DEFAULT 'grid';
```

| 欄位 | 類型 | 說明 |
|------|------|------|
| status | VARCHAR(20) | 'draft' / 'published' |
| developers | JSONB | 開發者 user_secure_code 陣列，如 `["abc123", "def456"]` |
| layout_mode | VARCHAR(20) | 'grid'(宮格) / 'free'(GridStack 自由) |

### 2.3 可見性規則

- **開發者名單（developers）**：建立者自動加入，可手動管理（預留多人開發）
- **DRAFT 狀態**：只有 developers 名單中的用戶 + 系統管理員/企業管理員可見
- **PUBLISHED 狀態**：依現有 module_access_control + 角色控制 menu 可見性（已驗證可用）
- **設計器入口**：從「我的開發案」列表進入，不經 menu

### 2.4 Model 變更 -- DcSubSystem

```python
# 新增欄位
status = Column(String(20), default='draft', nullable=False)
developers = Column(JSONB, default=list)
layout_mode = Column(String(20), default='grid', nullable=False)
```

---

## 三、統一設計器介面 (Studio)

### 3.1 URL

```
/nocode-builder/studio/<sub_system_sc>
```

### 3.2 佈局結構

```
+------------------------------------------------------------------+
| header: 子系統名稱 | 儲存 | 預覽 | 發布                            |
+------------------+-----------------------------------------------+
| 左側邊欄          | 設計區 (右側主區)                                |
| +--------------+ | +-------------------------------------------+ |
| | 元件庫        | | |                                           | |
| | - DATALIST   | | |  佈局設計區                                 | |
| | - MENU (未來) | | |  (Grid 宮格 或 GridStack 自由佈局)            | |
| |              | | |                                           | |
| +--------------+ | |                                           | |
| | Site Map 樹   | | +-------------------------------------------+ |
| | > 首頁        | | 屬性面板 (選中元件時展開)                        |
| | > 客戶管理    | | +-------------------------------------------+ |
| |   - 客戶清單  | | | View 選擇 | CRUD 設定 | Context 綁定        | |
| |   - 訂單查詢  | | | 權限白名單 | 資料篩選                        | |
| | > 報表        | | +-------------------------------------------+ |
| +--------------+ |                                               |
+------------------+-----------------------------------------------+
```

### 3.3 互動流程

1. 進入 Studio → 載入子系統資訊 + Site Map 樹
2. 若無 Site Map 節點 → 提示建立第一個頁面
3. 點擊樹節點 (page 類型) → 右側載入該頁面的佈局設計
4. 從元件庫拖放/點擊加入元件到設計區
5. 點擊已放置的元件 → 下方展開屬性面板設定
6. 儲存 → 寫入對應的 DcPageLayout
7. 右鍵/按鈕操作樹節點 → 新增/刪除/重命名/排序
8. 在樹節點上設定權限白名單 (透過屬性面板或右鍵選單)

### 3.4 兩種佈局模式

建立子系統時選擇，存入 `dc_sub_systems.layout_mode`：

#### Grid 宮格模式 (預設，適合一般用戶)

- 初始提供 4x4 = 16 格，另可選 3x3 = 9 格
- 用戶可合併相鄰格子（類似 Excel 合併儲存格）
- 用戶可刪除不需要的格子
- 技術實作: CSS Grid + 自建合併邏輯
- 格子確定後，每格放一個元件

**操作方式：**
1. 顯示 4x4 格子，每格有格子編號
2. 點擊格子 A → 按住 Shift 點擊格子 B → 合併（必須相鄰且構成矩形）
3. 右鍵格子 → 刪除 / 取消合併
4. 確定佈局後，拖放元件到格子中

**layout_json 格式 (Grid 模式 v3)：**
```json
{
    "version": 3,
    "mode": "grid",
    "gridSize": [4, 4],
    "zones": [
        { "id": "z1", "row": 1, "col": 1, "rowSpan": 1, "colSpan": 1 },
        { "id": "z2", "row": 1, "col": 2, "rowSpan": 1, "colSpan": 3 },
        { "id": "z3", "row": 2, "col": 1, "rowSpan": 3, "colSpan": 1 },
        { "id": "z4", "row": 2, "col": 2, "rowSpan": 3, "colSpan": 3 }
    ],
    "widgets": [
        { "zoneId": "z1", "widget": { "type": "DATALIST", "viewCode": "...", ... } },
        { "zoneId": "z4", "widget": { "type": "DATALIST", "viewCode": "...", ... } }
    ]
}
```

#### GridStack 自由模式 (進階用戶)

- 沿用現有 lab-designer.js 的 GridStack 邏輯
- 12 欄自由拖放，像素級定位
- 適合有設計經驗的用戶

**layout_json 格式 (維持 v2 不變)：**
```json
{
    "version": 2,
    "widgets": [
        { "x": 0, "y": 0, "w": 6, "h": 5, "id": "w_abc",
          "widget": { "type": "DATALIST", "viewCode": "...", "contextOutputs": [...], "contextInputs": [...] }
        }
    ]
}
```

### 3.5 元件清單 (Phase 2)

| 元件 | 說明 | 狀態 |
|------|------|------|
| DATALIST | 資料表 CRUD 元件 | 已有，復用 DataListWidget |
| MENU | 導航選單（讀 Site Map） | 未來開發 |

> 不做靜態標題文字元件。

---

## 四、開發案管理 (Phase 1)

### 4.1 「我的開發案」列表頁

**URL**: `/nocode-builder/my-projects`

顯示當前用戶的所有開發案（developers 名單包含自己的 + 系統管理員/企業管理員看全部）。

| 欄位 | 說明 |
|------|------|
| 名稱 | 子系統名稱 |
| 狀態 | DRAFT / PUBLISHED |
| 佈局模式 | Grid 宮格 / GridStack 自由 |
| 建立時間 | created_at |
| 操作 | 進入 Studio / 刪除 |

### 4.2 建立開發案

建立時需填寫：

| 欄位 | 必填 | 說明 |
|------|------|------|
| 名稱 | 是 | 子系統名稱，如「訂餐系統」 |
| 說明 | 否 | 開發目的描述 |
| 佈局模式 | 是 | Grid 宮格(預設) / GridStack 自由 |

**自動處理：**
- 自動建立對應的 OrganizationalUnit (type=GROUP) 作為社群
- 建立者自動加入 developers 名單
- 建立者自動成為社群 MANAGER
- status 設為 DRAFT

### 4.3 API

| 方法 | 路由 | 說明 |
|------|------|------|
| GET | `/api/nocode-builder/projects` | 我的開發案列表 |
| POST | `/api/nocode-builder/projects` | 建立開發案 |
| PUT | `/api/nocode-builder/projects/<sc>` | 更新開發案資訊 |
| DELETE | `/api/nocode-builder/projects/<sc>` | 刪除開發案（軟刪除） |
| POST | `/api/nocode-builder/projects/<sc>/publish` | 上線 |
| POST | `/api/nocode-builder/projects/<sc>/unpublish` | 下線 |
| GET | `/api/nocode-builder/projects/<sc>/developers` | 開發者名單 |
| POST | `/api/nocode-builder/projects/<sc>/developers` | 新增開發者 |
| DELETE | `/api/nocode-builder/projects/<sc>/developers/<user_sc>` | 移除開發者 |

---

## 五、row-form.js Context Headers 修正 (P1 安全)

### 5.1 問題

row-form.js 在 POST/PUT 資料時沒有傳遞 `X-SiteMap-Node` / `X-SubSystem-SC` headers，
導致後端 `_check_sub_system_crud()` 無法執行 CRUD 權限檢查。

### 5.2 修正方案

**datalist-widget.js 開新分頁時，URL 帶上 context 參數：**
```javascript
// datalist-widget.js 中
btn.href = '/nocode-builder/views/' + viewCode + '/rows/' + rowId + '/edit'
    + '?_ss=' + encodeURIComponent(this.config._subSystemSc || '')
    + '&_smn=' + encodeURIComponent(this.config._siteMapNodeSc || '');
```

**row-form.js 讀取 URL 參數，在 POST/PUT 時附加 headers：**
```javascript
// row-form.js 中
const urlParams = new URLSearchParams(window.location.search);
const subSystemSc = urlParams.get('_ss');
const siteMapNodeSc = urlParams.get('_smn');

// fetch 時
headers['X-SubSystem-SC'] = subSystemSc;
headers['X-SiteMap-Node'] = siteMapNodeSc;
```

**新增資料同理：**
```javascript
btn.href = '/nocode-builder/views/' + viewCode + '/rows/new'
    + '?_ss=' + ... + '&_smn=' + ...;
```

---

## 六、Portal 用戶端 (維持現有)

Portal V2 (sub_system_portal_v2.html + site-map-portal.js) 維持現有邏輯不動。

它負責**用戶端瀏覽**，Studio 負責**開發端設計**，兩者職責分離。

Portal V2 需要支援兩種 layout_json 格式：
- v2 (GridStack 自由): 用現有 GridStack staticGrid 渲染
- v3 (Grid 宮格): 用 CSS Grid 渲染

在 site-map-portal.js 的 `loadPage()` 中根據 `layout.mode` 判斷渲染方式。

---

## 七、開發計劃

### Phase 1: 子系統狀態機 + 開發者可見性

**DB 變更：**
- Migration 006: dc_sub_systems 加 status/developers/layout_mode 欄位

**後端：**
- DcSubSystem Model 加欄位
- 新增 ProjectService（開發案管理邏輯）
- 新增 project_api.py（開發案 API）
- 修改 SubSystemService：DRAFT 狀態可見性過濾

**前端：**
- 新增 `my_projects.html` + `my-projects.js`（我的開發案列表）
- 新增 Web Route: `/nocode-builder/my-projects`

**驗證：**
- 建立開發案 → 只有開發者可見
- 上線後 → menu 出現，依角色控制可見

### Phase 2: 統一設計器 (Grid 宮格模式優先)

**前端：**
- 新增 `studio.html`（統一設計器頁面，CSS Grid 佈局）
- 新增 `studio.js`（整合邏輯）
- 新增 `grid-layout-editor.js`（Grid 宮格編輯器）
- 新增 `studio.css`（設計器樣式）
- 新增 Web Route: `/nocode-builder/studio/<sub_system_sc>`

**復用：**
- Site Map 樹操作邏輯（從 site-map-editor.js 抽取）
- DataListWidget（直接復用）
- PageContext（直接復用）
- Site Map API（全部不動）
- Page Layout API（全部不動）

**Grid 宮格編輯器核心邏輯：**
1. 渲染 NxN 格子（CSS Grid）
2. 格子合併（Shift+Click 選取 → 合併按鈕）
3. 格子刪除（右鍵選單）
4. 拖放元件到格子
5. 產出 layout_json v3 格式

**驗證：**
- 建立 Site Map → 點擊節點切換頁面 → 拖入 DATALIST → 設定 View → 儲存 → 預覽

### Phase 3: 上線申請流程

> 由用戶設計表單流程，此規格僅定義需要的欄位。

**申請單建立 menu 選項需要的資訊：**

| 欄位 | 來源 | 寫入目標 |
|------|------|---------|
| 子系統名稱 | dc_sub_systems.name | menu_items.title |
| 選單代碼 | 自動產生或手動輸入 | menu_items.code |
| 圖示 | dc_sub_systems.icon | menu_items.icon |
| 子系統 SC | dc_sub_systems.secure_code | menu_items.url 參數 |
| 申請人 | 自動 | 簽核用 |
| 申請說明 | 手動輸入 | 簽核用 |

**開發案提供的資訊（供填寫申請單）：**
Studio 設定頁面顯示子系統 secure_code、名稱、圖示等，方便複製到申請單。

### Phase 4: GridStack 自由模式整合

**前端：**
- studio.js 支援 layout_mode 判斷，載入不同編輯器
- Grid 模式 → grid-layout-editor.js
- Free 模式 → 復用現有 lab-designer.js 的 GridStack 邏輯（整合進 studio.js）

**Portal V2 渲染擴充：**
- site-map-portal.js 的 loadPage() 根據 layout.mode 判斷渲染方式

---

## 八、檔案清單 (預計新增/修改)

### 新增檔案

| 檔案 | 用途 |
|------|------|
| `modules/nocode_builder/migrations/006_sub_system_status.sql` | DB 遷移 |
| `modules/nocode_builder/services/project_service.py` | 開發案管理服務 |
| `modules/nocode_builder/api/project_api.py` | 開發案 API |
| `modules/nocode_builder/templates/modules/nocode_builder/my_projects.html` | 我的開發案列表 |
| `modules/nocode_builder/static/modules/nocode_builder/js/my-projects.js` | 列表邏輯 |
| `modules/nocode_builder/templates/modules/nocode_builder/studio.html` | 統一設計器頁面 |
| `modules/nocode_builder/static/modules/nocode_builder/js/studio.js` | 設計器邏輯 |
| `modules/nocode_builder/static/modules/nocode_builder/js/grid-layout-editor.js` | Grid 宮格編輯器 |
| `modules/nocode_builder/static/modules/nocode_builder/css/studio.css` | 設計器樣式 |

### 修改檔案

| 檔案 | 變更 |
|------|------|
| `modules/nocode_builder/models/sub_system.py` | 加 status/developers/layout_mode 欄位 |
| `modules/nocode_builder/web/__init__.py` | 加 /my-projects, /studio 路由 |
| `modules/nocode_builder/api/__init__.py` | 註冊 project_api blueprint |
| `modules/nocode_builder/static/modules/nocode_builder/js/datalist-widget.js` | 開新分頁帶 context 參數 |
| `modules/nocode_builder/static/modules/nocode_builder/js/row-form.js` | 讀取 context 參數附加 headers |
| `modules/nocode_builder/static/modules/nocode_builder/js/site-map-portal.js` | 支援 v3 Grid 佈局渲染 |

### 不動的檔案

| 檔案 | 理由 |
|------|------|
| site_map_api.py | API 已完整 |
| site_map_service.py | 邏輯已完整 |
| site_map_node.py / site_map_permission.py | Model 不變 |
| page_layout.py | Model 不變 |
| sub_system_service.py | 權限邏輯不變 |
| page-context.js | 復用 |
| datalist-widget.js (除 context 修正外) | 復用 |

---

## 九、現有頁面處理

| 頁面 | 處理方式 |
|------|---------|
| lab.html + lab-designer.js | 保留，Phase 4 整合後評估廢棄 |
| sub_system_config.html (Site Map Editor) | 保留，Studio 做好後評估廢棄 |
| sub_system_portal_v2.html | 保留（用戶端瀏覽用） |
| sub_system_list.html | 被 my_projects.html 取代，但保留 |
| sub_system_portal.html (V1) | 保留（向下相容） |

---

## 十、安全規範遵循

- TENANT-01: 所有查詢強制 org_secure_code 過濾
- AUTH-02: Studio 路由使用 @login_required + 開發者名單檢查
- DATA-01: 用戶查詢過濾 is_deleted=False, is_active=True
- FRONT-03: 不硬編碼 node type
- FRONT-01: JS/CSS 分離為獨立檔案

---

*規格書結束*
