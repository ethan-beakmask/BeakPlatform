-- 009: DcSubSystem 加入來源申請單號欄位
-- 用途：記錄由 SubSystemProvision 節點自動建立時的表單 serial_number

ALTER TABLE dc_sub_systems
    ADD COLUMN IF NOT EXISTS provision_serial_number VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_dc_sub_systems_provision_serial
    ON dc_sub_systems (provision_serial_number)
    WHERE provision_serial_number IS NOT NULL;
