-- 011: 移除過時節點定義 FormExp, Notification
-- 這兩個節點已被其他機制取代，從未實作 handler，從設計器中移除

DELETE FROM workflow_node_definitions WHERE node_type = 'FormExp';
DELETE FROM workflow_node_definitions WHERE node_type = 'Notification';
