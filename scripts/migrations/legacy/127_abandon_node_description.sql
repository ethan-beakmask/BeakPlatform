-- 127: 更新 Abandon 節點的 description，讓設計者能分辨它與 End(cancel) 的差異
-- 建立日期: 2026-08-31
-- 背景：dev-notes/ABANDON_SPEC.md（PF-xx，Abandon 節點盤點）
--
-- 舊描述「強制中止流程」完全看不出與 End 節點的差別（End 也能選「取消」模式）。
-- 新描述說明：1) 固定等同 End 的取消模式 2) 子流程情境下會標記異常終止，
-- 但目前流程變數尚未支援讀取這個標記（誠實告知現況，避免設計者誤用）。
--
-- 這支 migration 只更新既有 DB 記錄。新環境的出廠預設另外同步於
-- modules/form_workflow/migrations/013_seed_node_definitions.sql（見同一次提交）。

BEGIN;

UPDATE workflow_node_definitions
SET description = '強制中止流程並取消所有未完成節點，等同 End 節點的「取消」模式。'
                   '子流程走此節點時，父流程會收到異常終止的內部標記'
                   '（目前僅寫入紀錄，流程變數尚未支援讀取此標記）。',
    updated_at = NOW()
WHERE node_type = 'Abandon';

COMMIT;
