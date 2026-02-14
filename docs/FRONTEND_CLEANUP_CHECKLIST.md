# 前端整理進度追蹤 (HTML 瘦身)

> 目標：所有模板符合 FRONT-01/02 規範（500 行上限，無大段內嵌 JS/CSS）

## 狀態說明
- [x] 已完成
- [ ] 待處理
- [-] 進行中

---

## Phase 0: 基礎建設
- [x] `backend/app/static/css/common.css` — 共用樣式（[x-cloak], .section-title, .modal-overlay, .toast, .form-row）
- [x] `layouts/base.html` — 加入 common.css 引用
- [x] `docs/FRONTEND_CLEANUP_CHECKLIST.md` — 本文件
- [x] 關閉 Forgejo Issue #11（Bulma CSS 風格統一化已無需進行）

## Phase 1: 快速勝利（零 Jinja2 耦合）
| 模板 | 原始行數 | 瘦身後行數 | CSS 檔 | JS 檔 | 狀態 |
|------|----------|-----------|--------|-------|------|
| `template_list.html` | 700 | 244 | `template-list.css` | `template-list.js` | [x] |
| `workflow_list.html` | 674 | 296 | `workflow-list.css` | `workflow-list.js` | [x] |

## Phase 2: 中等難度（少量 Jinja2，Window Bridge）
| 模板 | 原始行數 | 瘦身後行數 | CSS 檔 | JS 檔 | 狀態 |
|------|----------|-----------|--------|-------|------|
| `holidays.html` | 1011 | 205 | `holidays.css` | `holidays.js` | [x] |
| `schedules.html` | 905 | 226 | `schedules.css` | `schedules.js` | [x] |
| `form_center.html` | 1880 | 393 | `form-center.css` | `form-center.js` | [x] |
| `form_designer.html` | 479 (含4 partial 共1938) | 133 | — (已有) | `form-designer-main.js` | [x] |

### Phase 2 額外產出
- `_form_center_list_view.html` — 表單中心清單模式 partial (~307 行)
- `_form_center_approval_modal.html` — 表單中心簽核模態框 partial (~117 行)
- 已刪除: `_monitor_methods.html`, `_read_form_methods.html` (合併入 form-center.js)
- 已刪除: `_designer_toast_init.html`, `_designer_background.html`, `_designer_preview_print.html`, `_designer_save_template.html` (合併入 form-designer-main.js)

## Phase 3: 高難度（多 Jinja2，需解耦）
| 模板 | 原始行數 | 瘦身後行數 | CSS 檔 | JS 檔 | 狀態 |
|------|----------|-----------|--------|-------|------|
| `groups.html` | 1305 | 238 | `org-tree.css` (共用) | `groups.js` | [x] |
| `users/create.html` | 930 | 256 | `user-form.css` | `user-form.js` | [x] |
| `departments.html` | 351 (含 393 行 CSS partial) | 351 | `org-tree.css` (共用) | — (保留 partial) | [x] |

### Phase 3 額外產出
- `org-tree.css` (467 行) — 部門/社群共用樣式（tree-panel, jstree, staff-layout, 拖放等）
- 已刪除: `_departments_styles.html` (搬入 org-tree.css)

## Phase 4: 批量處理剩餘 HIGH 檔案
| 模板 | 原始行數 | 狀態 |
|------|----------|------|
| `users/edit.html` | ~600 | [ ] |
| `users/view.html` | ~497 | [ ] |
| `numbering/edit.html` | ~451 | [ ] |
| `system_settings.html` | ~434 | [ ] |
| `org-admins/list.html` | ~391 | [ ] |
| `job_levels/matrix.html` | ~390 | [ ] |
| `external-users/edit.html` | ~373 | [ ] |
| `roles/create.html` | ~336 | [ ] |
| `pending_list.html` | ~317 | [ ] |
| `roles/edit.html` | ~298 | [ ] |
| `category_list.html` | ~379 | [ ] |
| `mappings_list.html` | ~623 | [ ] |
| `dashboard.html` | ~389 | [ ] |
| `dev/quick_login.html` | ~709 | [ ] |

## Phase 5: 收尾
- [ ] 刪除已轉為外部 .js 的死 partial 檔案
- [ ] 全模板合規審計（FRONT-01/02）
- [ ] 去重：common.css / app.css / 頁面 CSS 無重複
- [ ] 更新本文件標記完成

---

## 共用靜態檔案清單

### 平台層 (`backend/app/static/`)
| 檔案 | 用途 |
|------|------|
| `css/common.css` | 跨頁面共用樣式 |
| `css/app.css` | 原有應用樣式 |
| `css/themes.css` | 主題色系 |
| `css/holidays.css` | 假日設定頁 |
| `css/schedules.css` | 班表頁 |
| `css/org-tree.css` | 部門/社群共用樣式 |
| `css/user-form.css` | 新增/編輯用戶頁 |
| `js/app.js` | 原有應用 JS |
| `js/auth.js` | 認證相關 JS |
| `js/holidays.js` | 假日設定頁 |
| `js/schedules.js` | 班表頁 |
| `js/groups.js` | 社群設定頁 |
| `js/user-form.js` | 新增用戶頁 |

### 模組層 (`modules/form_workflow/static/modules/form_workflow/`)
| 檔案 | 用途 |
|------|------|
| `css/template-list.css` | 表單模板列表 |
| `css/workflow-list.css` | 工作流列表 |
| `css/form-designer.css` | 表單設計器 |
| `css/form-center.css` | 表單中心 |
| `css/workflow-designer.css` | 工作流設計器 |
| `js/template-list.js` | 表單模板列表 |
| `js/workflow-list.js` | 工作流列表 |
| `js/form-center.js` | 表單中心 |
| `js/form-designer-main.js` | 表單設計器主邏輯 |
| `js/workflow-main.js` | 工作流設計器主邏輯 |
| `js/workflow-tree-chart.js` | 樹系圖 |

*最後更新: 2026-02-15*
