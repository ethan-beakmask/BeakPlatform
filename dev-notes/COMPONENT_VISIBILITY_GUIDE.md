# 元件級顯示與權限控制指引 (Phase D)

定版日期：2026-07-18
相關文件：`PERMISSION_MODEL.md`（頁面級雙鑰匙）、`EGRESS_POLICY_SPEC.md`（資料出口）、`ACCESS_CENTER_SPEC.md`（權限管理中心）

---

## 1. 四層防線總表

平台的「誰能看見什麼、能做什麼」由四層機制組成，各層獨立運作、互相支援，**判定引擎分開、規範語彙統一**：

| 層 | 問題 | 機制 | 判定輸入 | 設定來源 |
|---|---|---|---|---|
| 1 頁面級 | 能不能進這頁 | PageRoleGuard 雙鑰匙（Key1 user_type + Key2 角色） | 角色 | /access/ Tab1 功能授權 |
| 2 UI 元件級 | 這頁裡看不看得到這顆按鈕 | `can()` Jinja global / `BkCaps` JS（本文件） | 角色 → permission code | /access/ Tab2 角色配權限 |
| 3 流程語境級 | 這一關卡看得到哪些表單欄位 | FormAdapter 節點 field_permissions + 伺服器端 schema 裁剪 | 流程語境（node + 開啟者與關卡關係） | 流程設計器節點屬性 |
| 4 資料出口級 | 這個欄位值露不露、怎麼露 | EGRESS-01 clear/masked/hidden | (角色, 語境) | 出口政策 |

**共同鐵律**：
- 三態語彙統一為 `editable / readonly / hidden`（按鈕是其退化版 visible/hidden；EGRESS 的 clear/masked/hidden 是資料值對應版）。
- **hidden 一律後端不出資料**——伺服器端不渲染 / 從回應剔除。前端條件顯示（`x-show`、form.io conditional）只准當體驗輔助，**不准當防線**（F12 可視）。
- UI 層永遠只是「鏡射」，真正防線在 API 層——就算前端被竄改，API 照樣 403。

---

## 2. UI 元件級（Phase D 核心）

### 2.1 設計原則

**不發明新權限模型。** 按鈕綁定它背後 API 所需的 permission code，UI 把 API 層既有判定提前渲染。設定來源就是 /access/ Tab2 的角色配權限，無獨立設定介面。

- permission code 沿用 API 層既有命名（如 `open_defense.decision.write`），不為 UI 另創。
- ORG_ADMIN 對非 SYSTEM 級權限自動通過（`PermissionService.check` 內建）；SYSTEM_ADMIN 走正常 RBAC（其角色已配權限）。
- 非資料裝飾元件不需控制。

### 2.2 後端模板（首選，天然防 F12）

```jinja2
{% if can('open_defense.decision.write') %}
  <button class="btn btn-sm btn-secondary" @click="revoke(d)">{{ _('撤銷') }}</button>
{% endif %}
```

`can(code)` 是 Jinja global（註冊於 `backend/app/__init__.py`），委派 `capability_service.user_can()`，per-request memoize。

### 2.3 前端 JS（Alpine 動態渲染時）

Window Bridge（模式 B）注入能力集，web route 端：

```python
from app.services.capability_service import build_caps
caps = build_caps(['open_defense.decision.write'])
return render_template('...html', page_caps=caps)
```

模板端（放在頁面 JS 引入之前）：

```html
<script>window.__PAGE_CAPS = {{ page_caps | tojson }};</script>
```

JS 端（`capability.js` 已在 base.html 全域載入）：

```javascript
if (!BkCaps.can('open_defense.decision.write')) return;   // fail-closed：未注入一律 false
```

Alpine 中控制元件存在性用 `x-if`，**禁止**用 `x-show` 當權限控制（DOM 仍在）。
獨立模板（不繼承 base.html）需自行引入 `/static/js/capability.js`。

### 2.4 API 層（真正防線）

單頁專屬資料 API → 沿用 `@page_keys_required('<menu_code>')`（與頁面共用選單雙鑰匙）。
動作型 API → `@permission_required('<permission_code>')`：

```python
from app.services.capability_service import permission_required

@admin_bp.route('/decisions/<secure_code>/revoke', methods=['POST'])
@permission_required('open_defense.decision.write')
def revoke_decision_admin(secure_code):
    ...
```

未通過回 403 `{'success': False, 'error': 'permission_denied', 'message': ...}`。

### 2.5 開發規則（新頁面必守）

1. 動作按鈕（增刪改、簽核、撤銷等）一律包 `can()`，code 與其呼叫的 API 防護一致。
2. API 動作端點掛 `@permission_required`（或既有 permission 檢查），**不可只做 UI 隱藏**。
3. 新 permission code 在模組 `MODULE_INFO['permissions']` 宣告，`flask module sync` 同步。

### 2.6 試點實作（範例出處）

open_defense decisions 頁（commit 對應 Phase D1）：
- `backend/app/services/capability_service.py` -- user_can / build_caps / permission_required
- `backend/app/static/js/capability.js` -- BkCaps
- `modules/open_defense/web/__init__.py` decisions() -- caps 注入
- `modules/open_defense/templates/modules/open_defense/decisions.html` -- [撤銷] 按鈕包 can()
- `modules/open_defense/api/admin/decisions.py` -- 兩支 API 換防護（原 @admin_required 退場）

---

## 3. 流程語境級（form_workflow 現況，2026-07-18 查證）

FormAdapter 簽核節點已內建三態欄位權限（無需新開發）：

- **設定**：流程設計器節點屬性（`wf-form-adapter.js` renderFieldPermissionsInTab），每欄位配 `editable/readonly/hidden`，分 **approver / reader** 身分，存節點 `config.field_permissions`。每關卡獨立設定 → 「A 關卡 A 君、B 關卡 B 君看不同元件」開箱即用。
- **執行**：`fc_pending.py` 依開啟者是否為 assignee 判 approver/reader，`fc_utils._apply_field_permissions_to_schema()` 伺服器端裁剪 form.io schema（未配置欄位預設 readonly）。
- **寫入防護**：簽核送出時後端過濾非 editable 欄位的改值。
- **最終守門**：EGRESS-01 `form_node` 語境（`egress_adapter.py`）接在欄位權限之後，支援 per-node_key 政策。

**資料防線（Forgejo Issue #27，已修復，commit 21f22e0b）**：schema 裁掉 hidden 元件的同時，`form_data` 亦同步剔除 hidden 欄位的頂層 key（`fc_pending.py`，須在 `apply_form_egress` 之後執行，因其內部重讀 `form_instance.form_data`）。egress form_node 政策為疊加的最終守門，順序不變。

**form.io 升級彈性**：裁剪邏輯全部外置於後端函式（輸入 schema JSON → 輸出裁剪後 schema），不修改 form.io 原始碼、不依賴其版本內部行為。form.io 只渲染收到的東西，升級不影響此層。

---

## 4. NoCode_Builder 重寫時的消費指引

NoCode_Builder 重寫（時程在後）**不需要自建權限機制**，直接消費四層現成能力：

1. 產生的頁面掛 url 型選單 → 頁面級雙鑰匙自動生效（Phase B 規則：不掛身分 decorator）。
2. 頁面內動作元件 → 綁 permission code，渲染時用 `can()` / `BkCaps`。
3. 動態表單元件 → 走 form_workflow 的 schema 裁剪模式（三態、伺服器端裁剪）。
4. 資料欄位 → 資源掛 EGRESS-01 出口政策。

如此 NoCode_Builder 定位收斂為「純頁面組裝器」，權限一致性由平台保證。
