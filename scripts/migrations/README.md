# migrations 已廢止（2026-09-01，PF-168）

**Schema 的唯一權威是 ORM model（`db.create_all()`）。本目錄不再有任何會被執行的東西。**

## 現況

- 全新安裝：`scripts/init_database.sh` 或 `scripts/install.sh` → `db.create_all()`
  ＋ `scripts/sql/` 的 DB 物件與出廠資料（fw_sp schema、節點型別定義、
  受限節點授權、出廠預設值）
- 更新：`install.sh --update` → `create_all`（只補新表）＋ 同一批冪等 seed
- 守恆機制：`scripts/check_schema_drift.sh` 比對「乾淨安裝庫 vs dev 庫」，
  有差就紅——改 model、加表、動 DB 物件之後跑一次
- `schema_migrations` 表已於 2026-09-01 自 dev 庫刪除（登記早已失真）

## 開發時改 schema 的規則

1. 改 ORM model（新表會被 create_all 建出來）
2. dev 庫用一次性 SQL/腳本原地跟上（執行完丟進 `legacy/` 留檔即可，無登記機制）
3. 跑 `bash scripts/check_schema_drift.sh` 確認兩邊一致
4. 動了節點型別定義要重跑 `scripts/export_node_definitions_seed.py`

## legacy/ 是什麼

2026-09-01 之前的完整 migration 歷史（001–136、`run_migrations.py`、
form_workflow 與 nocode_builder 的模組 migrations），僅供考古，
**不要對任何資料庫執行**。最後一支 `136_pf168_dev_convergence.sql`
是 dev 庫收斂到 model 權威時的一次性轉換記錄。

欄位級的升級機制（公開後既有環境的 schema 升級）目前刻意不存在——
2026-09-01 時點不存在任何已安裝的外部環境。首次需要時另行設計
（候選：alembic autogenerate），不要復活 `run_migrations.py`。
