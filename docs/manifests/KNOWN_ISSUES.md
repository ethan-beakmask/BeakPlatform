# BeakPlatform 已知問題與解法集

紀錄重複發生的問題，避免每次對話重新踩坑。
定期 review 時更新此文件。

---

## 格式

每個問題條目：
```
### [編號] 問題簡述
- **分類**: 安全 | 租戶 | UI | 資料 | 效能
- **頻率**: 高/中/低
- **症狀**: 用戶看到什麼
- **根因**: 為什麼發生
- **解法**: 正確做法
- **防雷**: manifest 中的哪個檢查點能預防
- **首次發現**: 日期
```

---

## 問題清單

### KI-001 選單點擊無反應
- **分類**: 資料
- **頻率**: 高
- **症狀**: 選單項目顯示但點擊後跳到 `#` 或無反應
- **根因**: menu_items 表的 link_type 設定錯誤（如用 `path` 而非 `url`）
- **解法**: 查 DB 確認 link_type 是否為 url/route/page/divider/header 之一
- **防雷**: CLAUDE.md MENU-01 規範
- **首次發現**: 2026-02

### KI-002 新選單項目一般用戶看不到
- **分類**: 安全
- **頻率**: 高
- **症狀**: 管理員能看到選單，企業成員看不到
- **根因**: 只設了 MenuPermission（Key1），沒設 MenuRoleRequirement（Key2）
- **解法**: 在 menu_role_requirements 表為該選單設定角色需求（含 org_secure_code）
- **防雷**: SECURITY_PITFALLS.md #3
- **首次發現**: 2026-02

### KI-003 跨企業資料洩露
- **分類**: 安全/租戶
- **頻率**: 中
- **症狀**: 企業 A 的管理員能看到企業 B 的資料
- **根因**: 查詢時忘記加 org_secure_code 過濾
- **解法**: 所有查詢經 ResourceGateway 或明確加 org_secure_code
- **防雷**: SECURITY_PITFALLS.md #1
- **首次發現**: 2026-01

### KI-004 時間顯示為 UTC
- **分類**: UI
- **頻率**: 中
- **症狀**: 頁面上的時間比實際慢 8 小時
- **根因**: 用 .strftime() 而非 |tz_format 或 BkTime.format()
- **解法**: 後端用 |tz_format，前端用 BkTime.format()
- **防雷**: SECURITY_PITFALLS.md #5，CLAUDE.md TZ-01
- **首次發現**: 2026-02

### KI-005 已停用帳號出現在列表中
- **分類**: 資料
- **頻率**: 中
- **症狀**: 停用或刪除的帳號仍出現在用戶列表、下拉選單
- **根因**: 查詢時忘記加 is_deleted=False 和 is_active=True
- **解法**: 所有用戶查詢都加雙重過濾
- **防雷**: SECURITY_PITFALLS.md #2，CLAUDE.md DATA-01
- **首次發現**: 2026-01

---

## 待觀察

（使用一陣子後，根據實際發生的問題新增）

---

*最後更新: 2026-03-27*
*下次 review: 使用 2~4 週後*
