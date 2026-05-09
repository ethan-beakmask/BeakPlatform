# OpenDefense 快速上手

> 給 BeakPlatform 管理員的「我打開 /menu/ 看到四個項目要從哪做起」說明。
> 詳細對外契約另見 `docs/integrations/open_defense_contract.md`。

---

## 一張圖看完整體角色

```
                 [外面的偵測工具]                    [外面的執行工具]
                Suricata / Coraza /                CrowdSec /
                Falco / Vector …                   nftables / Cloudflare …
                       │                                   ▲
                       │ 推 OCSF 事件(用                  │ 拉決策(用
                       │ 「事件接收金鑰」簽章)              │ 「執行端帳號」登入)
                       ▼                                   │
        ┌─────────────────── BeakPlatform ───────────────────┐
        │                                                     │
        │   收到事件  →  啟動表單流程  →  人/規則決策  →  寫決策表  │
        │                                                     │
        └─────────────────────────────────────────────────────┘
                       ▲                                   ▲
                       │                                   │
                  「決策列表」可看每筆        「儀表板」顯示總覽
                  狀態,可手動撤銷
```

**白話**:這個模組讓 BeakPlatform 變成兩個「外部世界」之間的決策中介:

- **「事件接收金鑰」**(IK)= 開門讓**告警進來**的門票,給偵測工具用。
- **「執行端帳號」**(SA)= 開門讓**動作出去**的門票,給執行工具用。
- **「決策列表」**= 進出之間產生的所有決策紀錄,可查可撤。
- **「儀表板」**= 上面三件事的數字總覽。

---

## 四個選單的關係

| 選單 | 給誰用 | 何時會看 |
|---|---|---|
| 事件接收金鑰 | **偵測工具**(對方端) | 一開始給對方一把,撤銷時回來這裡 |
| 執行端帳號 | **執行工具**(對方端) | 一開始給對方一把,撤銷時回來這裡 |
| 決策列表 | **你自己**(查紀錄、人工撤銷) | 平常監看時 |
| 儀表板 | **你自己**(看數字) | 巡檢時瞄一眼 |

---

## 第一次設定的順序(只做一次)

### 步驟 1:建一把「事件接收金鑰」給偵測端

開 **/open-defense/intake-keys** → `+ 新增金鑰`

填:
- **名稱**:辨識用,如「sec-vm 安全堆疊」
- **允許的 source_system**:勾選對方會推進來的工具(suricata / coraza / falco …)
- **過期時間**:留空 = 永不過期

按建立後,畫面會跳出 **黃色框框**顯示 `key_id` 和 `secret_b64`。
**這是唯一一次顯示 secret**,關掉就再也看不到。
複製這兩個值,用安全管道(LINE 私訊 / 加密郵件)交給對方端負責人。

對方拿到後就能簽章推事件進來。

### 步驟 2:建一個「執行端帳號」給執行端

開 **/open-defense/service-accounts** → `+ 新增帳號`

填:
- **名稱**:辨識用,如「sec-vm CrowdSec executor」
- **SA ID 提示**:可選,如填 `executor_secvm_01`,最終 ID 為 `sa_executor_secvm_01_<6 hex>`
- **允許的 enforcement_points**:勾對方會處理的(crowdsec / nftables / cloudflare …)。空白 = 全部允許,但建議只勾用得到的。

按建立後,**黃色框框**顯示 `sa_id` 和 `sa_secret_b64`。
**同樣只顯示一次**,複製給對方。對方用這組帳密呼叫 `POST /sa/login` 取 JWT 後就能拉決策。

### 步驟 3:設定 event_class → 表單模板對應(目前需用 SQL)

對方推事件進來時,平台要知道用哪個表單模板處理。目前**沒有 UI**,需 SQL 直接寫:

```sql
-- 為 web_activity 類型的事件指定處理表單
INSERT INTO od_form_template_mappings
  (secure_code, org_secure_code, event_class, form_template_secure_code, note,
   created_at, updated_at, is_deleted)
VALUES
  (substr(md5(random()::text),1,32),
   '<your_org_secure_code>',
   'web_activity',                -- 事件類型
   '<form_template_secure_code>', -- 在「表單流程 → 表單範本」找到並複製 sc
   'Web 攻擊事件處理流程',
   NOW(), NOW(), false);
```

`event_class` 共 4 種:`web_activity` / `network_activity` / `process_activity` / `detection_finding`。
每種要進來都要先有對應,否則會回 422 `no_mapping`。

> 表單模板必須先在「表單流程 → 表單範本」**發行(Published)**,webhook 才接得起來。

---

## 平常運作時看哪裡

### 「儀表板」/open-defense/dashboard

最常看,9 張統計卡:
- **待執行**:有沒有決策卡住沒人拉(>0 一段時間 = 執行端死了)
- **失敗**:執行端報失敗的(>0 = 對方沒處理好,要查)
- **今日收到事件**:偵測端有沒有正常推
- **今日簽發決策**:案件流程有沒有正常產決策
- **啟用金鑰 / 啟用執行端帳號**:當前掛了幾組對外整合

底下兩欄:
- **最近事件**:剛收到的 5 筆告警
- **待執行決策**:現在等執行端拉的 5 筆動作

### 「決策列表」/open-defense/decisions

能做的事:
- **篩選** status / action / target IP 字串
- **手動撤銷** applied 狀態的 block 決策(會立即產生對應 unblock 給執行端拉走)
- 看執行端回報的結果(`applied_by` 欄位 = 是誰落地的;`error_message` = 失敗原因)

**狀態解讀**:

| 狀態 | 意義 |
|---|---|
| pending | 等執行端拉走 |
| picked_up | 執行端說「我拿走了,正在做」 |
| applied | 執行端說「做完了」 |
| partial | 多個 enforcement_point 中有的成功有的失敗 |
| failed | 執行端說「失敗了」 |
| expired | TTL 到期,系統自動標 + 產 unblock 決策 |
| revoked | 你手動撤銷的 |

---

## 常見情境

### 對方 detector 推事件回 401

→ 對方 secret 錯 / 時間沒同步 / 用了已撤銷的 key。
→ 開「事件接收金鑰」看那把是不是還在 `啟用` 狀態。失效就重發一把。

### 對方 executor 拉決策回 401

→ JWT 過期(15 分鐘),對方該重新 `POST /sa/login`。或對方帳號被你撤了。
→ 開「執行端帳號」看狀態,顯示 `鎖定中` 就按「解鎖」(對方是不是密碼打錯 5 次?)。

### 看到一筆 applied 但其實不該擋,要立刻撤

→ 開「決策列表」找到那筆 → 按「撤銷」→ 填理由(會記錄是誰撤的)。
→ 系統自動寫一筆 unblock,對方執行端 5 秒內拉到、立即解阻擋。
→ 原決策狀態變成 `revoked`。

### 自動過期解封的時序

```
T+0    block 寫進來,TTL=600 秒
T+1s   對方拉走,nft 加規則
T+1s   PATCH applied
T+600s 規則自動失效(kernel 自己倒數)
T+601s BP 每分鐘 cron 偵測過期 → 寫 unblock(pending)+ 標原決策 expired
T+606s 對方拉走 unblock,nft del 規則(可能已不存在,屬正常)
T+606s PATCH applied
```

不需要人工介入,全自動。

---

## 安全提醒

- IK / SA 的 secret 一律 **只在建立時顯示一次**。複製後立刻離開那個視窗,不要截圖留檔。
- 給對方時,**用加密管道**(LINE 私訊、密碼保護的 7z、密鑰管理服務),不要明文放在 email body 或聊天群。
- secret 一旦外流就直接到對應頁面**撤銷**,然後重發一把。
- 撤銷後對方的舊 secret 立即作廢(不需要等 cache 過期)。
