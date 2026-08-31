-- 128_abandon_move_to_basic.sql
--
-- Abandon 節點從「系統」分類移到「基本」分類，與 End 放在一起，並更新 description。
--
-- 緣由（Ethan 2026-08-31 提供的歷史脈絡）：Abandon 的原始設計動機是「最古老的版本
-- 只允許一個 End 節點，流程圖複雜時每條支線都拉一條線到 End 會太亂」。改成允許多個
-- End 之後那個理由已經消失，一度成為與 End(finish_mode='cancel') 完全等價的冗餘節點。
--
-- 同一天實作的終態差異（node_runner 的 data.workflow_status）給了它新的存在理由：
-- Abandon 是唯一會把流程與表單記成「已中止」的結束方式，End 的三種模式都記成完成
-- （表單顯示「已核准」）。既然它是一般結束方式之一而不是系統級能力
-- （require_system_admin=false、org_restricted=false，所有企業都看得到），
-- 放在「系統級管理員專用」分類本來就是錯的。
--
-- 冪等：可重複執行。
BEGIN;

UPDATE workflow_node_definitions
SET category = '基本',
    description = '異常終止：結束流程、取消所有未完成節點，並把流程與表單記為「已中止」。'
                  '與 End 的差別在終態——End 的三種模式都記為完成（表單顯示已核准），'
                  '只有本節點會記成已中止。',
    updated_at = NOW()
WHERE node_type = 'Abandon';

COMMIT;
