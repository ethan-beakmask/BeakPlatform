# 交接：Page IR v3 P4 -- NoCode 子系統 SQLite Resolver

（2026-07-27 建立，前情：P1-P3 已完成，commits 47a6f8f0 / 11b5597c / 428ca16e）

## 任務

依 `docs/PAGE_IR_SPEC.md` §6.3，為 NoCode 子系統實作第二種 L2 Binding Resolver：
IR 頁面在**子系統 portal 語境**下渲染時，資料只准來自該子系統專屬 SQLite，
帳號體系是 SQLite 內的 portal 帳號，**母系統（PostgreSQL）權限與資料完全不進入**。

動工前必讀：
1. `docs/PAGE_IR_SPEC.md`（總規格，重點 §1 三層、§4 綁定語法、§5 INV-1~7、§6 resolver 介面）
2. `backend/app/pageir/platform_resources.py`（P2 的 BeakPlatform resolver 範本，60 行）
3. `backend/app/pageir/registry.py`（register_resource 的 config 結構）
4. 既有 SQLite 基礎設施：`modules/nocode_builder/services/data_source_manager.py`、
   `sqlite_crud_service.py`、`portal_auth_service.py`（P4 要消費這些，不重造）

## 設計要點（先與用戶討論再定案）

1. **resource 註冊時機**：平台 resolver 是啟動時註冊一個 `user`；子系統的表是動態的
   （每個子系統一個 SQLite、表隨設計而異）→ 可能需要 registry 支援 prefix 型動態 resource
   （參考 egress_service.register_accessor_prefix 的先例）或 per-request 解析
2. **語境判定**：/p/ 的 v3 分支目前忽略 sub/ssp 參數（P2 刻意範圍外）；P4 要接回
   `_build_sub_system_context` + `_check_site_map_node_access` 那套（見
   `modules/nocode_builder/web/__init__.py` page_view 的 SEC-01 檢查）
3. **egress**：SQLite 資料無 EGRESS 政策（那是母系統 PostgreSQL 的表）→ resolver 的
   egress_resource 一律 None，欄位控制靠 fields 白名單；這是已知取捨，要寫進 SPEC
4. NoCode 安全模型細節用戶明言「開發 NoCode_Builder 時再討論」——P4 動工前先確認範圍

## 本 session 驗證過的可執行指令（原樣複製，新 session 照抄就通）

```bash
BASE=http://192.168.0.16:7000/beakplatform

# quick-login 取 admin session（CLAUDE.md 也有）
USC=$(PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -t -A \
  -c "SELECT secure_code FROM users WHERE email='admin-ethanyu@beluga.com' AND is_deleted=false;")
curl -s -c cj.txt -X POST "$BASE/dev/quick-login" -H 'Content-Type: application/json' -d "{\"user_id\":\"$USC\"}"

# 建 v3 草稿頁（不帶 layout_json 自動給 v3 最小文件）
curl -s -b cj.txt -X POST "$BASE/api/nocode-builder/pages" -H 'Content-Type: application/json' \
  -d '{"name":"P4-test"}'
# 回應 data.secure_code 即 <PSC>

# 設計器（瀏覽器）
# http://192.168.0.16:7000/beakplatform/nocode/ir-designer/<PSC>
# 草稿預覽（不需 published）
# http://192.168.0.16:7000/beakplatform/nocode/ir-designer/<PSC>/preview

# 發布（status 不能走 API，SQL 直改）
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev \
  -c "UPDATE dc_page_layouts SET status='published' WHERE secure_code='<PSC>';"
# 正式渲染: $BASE/p/<PSC>（需登入；v3 分支自動生效）

# 設計器 meta API（binding 下拉資料來源）
curl -s -b cj.txt "$BASE/api/pageir/meta"

# 測試（全部 22 案例）
cd /opt/BeakPlatform-dev/backend && ../venv/bin/python -m pytest \
  tests/test_pageir_p3.py tests/test_pageir_renderer.py tests/test_pageir_validator.py -q

# 服務重啟（Python/模板變更不自動重載）
sudo systemctl restart beakplatform-dev.service && systemctl is-active beakplatform-dev.service
```

## 冷讀補洞（2026-07-27 codex 冷讀後補入的環境事實）

- **SQLite 位置**：每子系統一目錄 `data/nocode_portals/<sub_system_sc>/`，內含 `portal.db`
  （帳號+角色+設定）與 `portal_data.db`（業務資料）。定位/初始化 API 見
  `data_source_manager.py` 的 `_get_portal_dir()` / `init_portal_sqlite()` / `has_sqlite()`
- **本機既有子系統**（`dc_sub_systems`，SQL：`SELECT secure_code, name FROM dc_sub_systems WHERE is_deleted=false;`）：
  `8uopl3mNbDzGDUGAcNQqNe` 匿名問卷-測試公開區子系統（此 SC 在 data/nocode_portals/ 已有 SQLite）、
  `x_ZCxTJZUIWSU25zxU_6DB` 子系統001、`Nu2I-Bn9j150e5i_prdSYc` 固定IP綁定申請 等
- **portal 入口**：blueprint `public_portal_bp` url_prefix `/public/portal`，登入路由
  `portal_login`（`modules/nocode_builder/web/portal_public.py:112`），帳號存 portal.db。
  portal 帳號/密碼本機沒有現成清單——測試時用 `init_portal_sqlite()` + portal 註冊流程自建
- **sub/ssp 參數**：`sub` = DcSubSystem secure_code、`ssp` = sub_system_page secure_code，
  組合檢查邏輯在 `_build_sub_system_context()`（`web/__init__.py:177`）
- **設計問題不在此檔解**：冷讀還列出的 meta API 動態表呈現、fields 白名單來源、
  /p/ 雙登入態分流、P4 驗收測試清單（跨子系統隔離/portal 帳號隔離/平台登入不得讀 SQLite）
  ——這些正是「動工前四個設計要點」要與用戶討論定案的內容，屬 P4 spec 的一部分，
  討論後寫進 codex spec 與 PAGE_IR_SPEC.md §6.3（EGRESS 取捨也補在 §6.3，不新增 INV）

## 已知限制（P3 驗收時登記）

- 設計器拖拉是 MVP：palette 點擊/拖放加入，節點重排靠上移/下移按鈕
- actions 的 action registry 尚無任何實際註冊（P2/P3 都以單元測試覆蓋機制）；
  第一個真 action 落地時要順便做 E2E
- form widget 有 submit_action_ref 但未註冊 → 整頁 422（fail-closed by design）
- /p/ 的 v3 分支不吃 sub/ssp 子系統參數（正是 P4 要接的）
