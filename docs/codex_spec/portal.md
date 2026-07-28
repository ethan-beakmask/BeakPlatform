## NoCode Portal 與 Page IR 規範（碰到子系統 portal 或 IR 渲染時適用）

### 兩個互斥的世界

| | platform | portal |
|---|---|---|
| 資料 | 母系統 PostgreSQL | 子系統 SQLite（`data/nocode_portals/<sub_sc>/`） |
| 身分 | Flask-Login `current_user` | `portal_users`（完全不同的帳號體系） |
| 語境 | `get_render_context()['world'] == 'platform'` | `... == 'portal'` |

**互斥是刻意的**：平台語境解析 `portal:` 資源一律回 None；
portal 語境解析平台資源也回 None。跨界一律 fail-closed。

`portal.db` = 帳號/群組/階級（敏感，不可當業務 CRUD 目標）；
`portal_data.db` = 業務資料表。

### 三層判定鏈（全部 AND，任一失敗回 404）

```
① 頁面級 DcSiteMapNode.access_matrix
   → portal_access_service.check_page_access()
② 掛載級 DcSubSystemPage.visible_roles
   → portal_public._portal_role_allowed()
③ 元件級 IR widget.access_matrix
   → check_widget_access()（read）/ check_widget_write_access()（create/update/delete）
```

判定規則：`(groups 為 null 或 user.group_code ∈ groups) AND (user.level_rank >= min_level 的 rank)`

### read 與 write 的語意刻意不同（弄錯就是安全破口）

| action | 未宣告時 |
|---|---|
| `read` | **放行**（不額外限制，上層仍有把關） |
| `create` / `update` / `delete` | **拒絕**（必須明確 opt-in） |

UI 措辭要讓使用者知道「沒啟用就是沒人能寫」，**不可**寫成「預設允許」。

### 權限判定失敗一律回 404

不洩漏存在與否。查原因看
`sudo journalctl -u beakplatform-dev.service --since "-5 min" | grep reason=`。

### fail-closed 清單（已實作，不可改成放行）

- `access_matrix` 格式錯 → 拒絕（不是忽略）
- `min_level` 指向不存在或停用的 level → 拒絕（不是當作 rank 0）
- portal.db 不存在 / 任何未預期例外 → 拒絕
- portal 語境找不到 access evaluator → 拒絕
- `fixed_filters` 在 portal 語境遇到平台變數（`$CURRENT_USER` 等）→ 拒絕整個查詢
  （只有 `$TODAY` 放行）

### 寫入還要再過兩道

1. `DcCrudView.allow_create / allow_edit / allow_delete`（view 層開關）
2. 可寫欄位三重交集：`binding.fields ∩ resource.fields ∩ _get_writable_columns(view)`，
   再過 `_strip_sensitive_columns()`，再**扣除有 mask 的欄位**

### 欄位遮罩

`backend/app/pageir/masking.py` 是 server 端唯一實作（partial / full / email / phone）。
遮罩必須在資料離開後端前套用；**禁止**前端 hover 揭示這類做法。
masked 欄位強制不可排序（含 query string 繞過）、不進 CRUD 表單、不可寫。

三個出口都要套：renderer `_prepare_table` / `_prepare_detail`、
portal rows API、寫入 API 的白名單。漏一個就是破口。

### Page IR schema

`backend/app/pageir/schema_v3.json` 是 single source of truth，
所有 `$defs` 都是 `additionalProperties: false`——**加新欄位必須先改 schema**，
否則驗證器直接擋下。`ir_version` 必須是 3（v2 已退役，`/p/` 遇到回 410）。

### portal 頁的外殼

真實 portal 頁用 `modules/nocode_builder/templates/modules/nocode_builder/portal_page_v3.html`
（獨立 HTML，**不繼承 base.html**，不含母體選單）。
平台語境的 IR 頁才用 `backend/app/templates/pageir/page_v3.html`（繼承 base.html）。
不要弄反。
