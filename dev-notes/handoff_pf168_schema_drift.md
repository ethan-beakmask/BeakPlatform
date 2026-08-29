# PF-168 交接：全新安裝與 dev 的 schema 分歧

> 2026-08-29 建立。本檔經 codex 冷讀審核後補齊（原版被指出 13 個需要猜測的地方）。
> 對應 BBN 待辦 **PF-168**（`note_search("PF-168")` 取最新狀態與 note）。

## 一、問題

平台有兩條建庫路徑，產出的 schema 不一樣，而且沒有任何機制會發現：

| 路徑 | 怎麼建表 |
|---|---|
| 全新安裝（外部使用者走這條） | `scripts/init_database.sh` → **`db.create_all()`**（從 ORM model 建表） |
| 本機 dev | 121 個 migration 疊出來的 |

開發者永遠只走後者，所以分歧不會被任何人發現——直到外部使用者裝起來、
用到某個功能才炸。

## 二、【這些要問 Ethan，不要自己決定】

動工前必須先取得決策，否則做出來的東西方向可能整個錯：

1. **`create_all` 與 migration 誰是權威？**
   兩邊互有領先：ORM model 落後於 migration（缺 5 個欄位），
   但 migration 又寫出了違反 TZ-01 的 `timestamptz`。
   （AI 的建議是以 ORM model 為權威、migration 只做資料轉換，理由是
   `create_all()` 已經是安裝路徑，而且 model 是開發時唯一會看的檔案。
   **這只是建議，尚未拍板。**）

2. **決定權威之後，另一邊怎麼處理？** 修歷史 migration／新增一支修正用
   migration／只保證未來正確？三種都做得到，代價不同。

3. **`schema_migrations` 失真要修成什麼樣？**
   補登 084 以後的 SQL migration／重建整張表／改 runner 邏輯／保留現狀當歷史？

4. **diff 腳本化之後放哪、誰呼叫？** 獨立腳本（`scripts/`）／併進
   `scripts/run_tests.sh`／做成 pytest 一條 case？

5. **修完之後允許哪些差異？**（驗收判準）
   目前假設 `schema_migrations` 不出現在 fresh 是預期的、
   3 張模組表**應該**要出現在 fresh。這兩條要確認。

## 三、現況（2026-08-29，PF-169 清理後實測）

### 3.1 缺表：4 張

```
fw_spec_schema                   modules/spec_formulate/models/spec_schema.py:43
fw_spec_schema_histories         modules/spec_formulate/models/spec_schema_history.py:18
fw_conglomerate_table_registry   modules/spec_formulate/models/conglomerate_table_registry.py:22
schema_migrations                登記表本身，create_all 不建屬預期
```

**這 3 張的 model 有被 `modules/spec_formulate/models/__init__.py` 正確 import
（第 8~10 行），問題不在 model 本身。**
成因是 `init_database.sh` 用 `SKIP_MODULE_SYNC=1` 跑 `create_all()`，
該旗標下 module_loader 不載入模組，那些 model 檔就沒被 import 到，
自然不進 SQLAlchemy metadata。**所以要改的是安裝流程，不是 model。**

（對照組：`org_encryption_keys` 是**平台** model，2026-08-29 已修
——model 檔存在但 `backend/app/models/__init__.py` 沒 import 它、
`crypto/key_manager.py` 又是函式內 lazy import。那是另一種成因，已解決。）

### 3.2 型別分歧：42 個欄位（完整清單）

**jsonb(dev) vs json(fresh)，16 個**

```
fw_column_display_config.config
fw_form_field_changes.new_value / old_value
fw_form_instances.builder_config / form_data / schema_snapshot
fw_form_templates.allowed_editors / builder_config / schema
fw_form_themes.component_defaults
fw_node_execution_queue.node_config / result
fw_sql_form_registries.column_mapping / form_schema
fw_workflow_instances.execution_log / graph_snapshot / variables
fw_workflow_templates.allowed_editors / cytoscape_config / graph
```

**bigint(dev) vs integer(fresh)，6 張表的主鍵 `id`**

```
dc_backgrounds  fw_categories  fw_mapping_permissions
fw_sql_form_registries  fw_workflow_backgrounds  store_installations  store_items
```

**timestamptz(dev) vs timestamp(fresh)，4 張表**（**錯的是 dev，違反 TZ-01**）

```
fw_categories.created_at / updated_at / deleted_at
fw_workflow_backgrounds.created_at / updated_at / deleted_at
password_reset_tokens.created_at / updated_at / deleted_at / expires_at / used_at / verified_at
user_unit_memberships.created_at / updated_at / deleted_at
```

### 3.3 欄位有無

**只在 dev 存在（5 個）**

```
fw_form_instances.title                                 character varying
fw_published_form_workflows.numbering_rule_secure_code  character varying
fw_workflow_instances.created_by_secure_code            character varying
fw_workflow_instances.timeout_at                        timestamp without time zone
fw_workflow_templates.timeout_minutes                   integer
```

（`fw_workflow_templates.timeout_minutes` 全專案沒有任何地方讀它，
見 CLAUDE.md「流程 graph 的引擎行為」表——決定去留時可以直接刪。）

**只在 fresh 存在（1 個）**

```
dc_bridge_logs.updated_at   timestamp without time zone
```

### 3.4 `schema_migrations` 已失真

檔案系統 118 個 migration / DB 登記 121 筆。084 以後的 SQL migration
**全數未登記**，DB 卻登記著檔案系統早已不存在的檔名
（`modules/form_workflow/*.sql` 等 20+ 筆）。
**這張表現在不能用來判斷「這個庫跑到哪一版」**，任何依賴它做增量升級的
想法都要先修這個。

## 四、怎麼重跑這份 diff

表清單比對的完整指令在專案 **CLAUDE.md**，搜「比對「乾淨安裝」與 dev 的 schema」，
整段可直接貼上執行（約 2 分鐘，2026-08-29 實際跑過四次）。

**欄位層級**把該節指令裡的查詢換成下面這句，其餘不變：

```sql
SELECT table_name||'.'||column_name||':'||data_type
FROM information_schema.columns WHERE table_schema='public';
```

比對腳本（產生本檔第三節那三份清單）：

```bash
python3 - <<'EOF'
d=set(x.strip() for x in open('/tmp/c_beakplatform_dev.txt') if x.strip())
f=set(x.strip() for x in open('/tmp/c_beakplatform_freshcheck.txt') if x.strip())
dt={x.split('.')[0] for x in d}; ft={x.split('.')[0] for x in f}
common=dt&ft
key=lambda x: x.rsplit(':',1)[0]
dk={key(x):x.rsplit(':',1)[1] for x in d-f if x.split('.')[0] in common}
fk={key(x):x.rsplit(':',1)[1] for x in f-d if x.split('.')[0] in common}
for k in sorted(set(dk)&set(fk)): print(f'型別分歧 {k}: dev={dk[k]} fresh={fk[k]}')
for k in sorted(set(dk)-set(fk)): print(f'只在 dev  {k}: {dk[k]}')
for k in sorted(set(fk)-set(dk)): print(f'只在 fresh {k}: {fk[k]}')
EOF
```

**兩個猜不到的**：

- 比對一律用 python 的 set 差集，**不要用 `comm`**——psql 的 `ORDER BY` 走
  collation，與 `sort` 的順序不一致，`comm` 會噴 "not in sorted order"
  並給出錯誤結果（2026-08-29 踩過）
- `beakplatform_freshcheck` 與 `beakplatform_test` 是不同的庫，
  跑測試時同時建它**不會**互相卡鎖（測試庫一次只能有一個使用者，
  但那條限制只管 `_test`）

## 五、留證與延伸閱讀

| 檔案 | 內容 |
|---|---|
| `/opt/tmp/verify/20260829-schema-drift-fresh-vs-dev.log` | 首次 diff 的原始輸出（清理前，缺 11 張時的狀態） |
| `/opt/tmp/verify/20260829-org-encryption-key-registration.log` | `org_encryption_keys` 修復前後對照 |
| `/opt/tmp/verify/20260829-pf169-dev-cleanup.log` | PF-169 清理，含清理對 drift 的收斂效果 |
| BBN atom **5297** | 「開發環境與全新安裝的 schema 會分歧」——通用方法論與檢查手法 |

**本檔第三節已是完整清單，log 不必讀也能動工**；log 只在需要對照
「清理前 vs 清理後」時才有用。
