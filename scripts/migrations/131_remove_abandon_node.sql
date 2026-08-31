-- 131_remove_abandon_node.sql
--
-- PF-200：Abandon 併入 End 後刪除（Ethan 2026-08-31 定調）。
-- End(finish_mode='cancel') 自此即「中止」語意：流程與表單記 CANCELLED，
-- 放在子流程時只中斷自己與所有下層（scope='subtree'）。
--
-- Abandon 使用量實查（2026-08-31）：模板 0、發行快照 0（共 55）、
-- 執行紀錄僅 1 筆 e2e 自造——零相容性成本，handler 與 factory 註冊已一併刪除
-- （與 ParallelFork 不同：ParallelFork 有 16 筆快照在用所以保留註冊，Abandon 沒有）。
-- 若在其他環境重跑本檔前發現有模板在用 Abandon，先把該節點改為
-- End(finish_mode='cancel') 再執行。
--
-- 冪等：重跑無害。

UPDATE workflow_node_definitions
SET is_deleted = true,
    is_active = false,
    deleted_at = (now() AT TIME ZONE 'UTC'),
    updated_at = (now() AT TIME ZONE 'UTC')
WHERE node_type = 'Abandon'
  AND is_deleted = false;
