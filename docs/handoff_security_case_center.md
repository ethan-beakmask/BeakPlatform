# 交接提示詞:資安案件處置中心(SOC)

> 把這份文件**整段貼給下一次對話的 Claude**(在 `/opt/BeakPlatform-dev/` 開的對話)。
> 我已經跑過完整脈絡,這份是壓縮的接手包。

---

## 你接手的脈絡

今天(2026-05-09)完成了 **OpenDefense 模組**:

```
[192.168.0.20 sec-vm]                    [192.168.0.16 BeakPlatform]
Suricata/Coraza/Falco/Vector ──HMAC──► /api/open_defense/intake
                                            ↓ 啟動 form_workflow
                                       od_defense_decisions 表
                                            ↑ JWT
CrowdSec/nftables/Cloudflare bridge ──pull/PATCH──┘
```

整套 detector → 中介 → executor 已端對端跑通(sec-vm Claude 配合驗收 6/6 burst 全綠)。

**你的任務**:基於 open_defense 之上,建一個專門的「**資安案件處置中心**」頁面,給 SOC 值班人員用。

---

## 必讀(按順序)

1. `CLAUDE.md` — 專案規範,manifest 流程、安全核心檔案、TZ-01、FRONT-01/03/07 等
2. `docs/integrations/open_defense_contract.md` — 對外契約 v1.0(已凍結,不要改)
3. `docs/manifests/mod-open-defense.yaml` — open_defense 模組地圖
4. `docs/open_defense_quickstart.md` — 4 個 UI 選單怎麼用(理解資料流)
5. `docs/manifests/mod-form-workflow.yaml` — form_workflow 引擎結構(你會大量用它)
6. `modules/open_defense/services/decision_service.py` — 決策表 CRUD(SOC 簽完要呼叫這個)
7. `modules/form_workflow/services/node_handlers/` — 既有節點(尤其是 `decision_writer_handler.py`、`alert_broadcast_handler.py` 當範本)

---

## 用戶需求(完整)

> 用本專案的表單中心(/forms/center)模式,製作一個資安案件處置中心(其實就是專門處理資安類表單,而原本的表單則將資安類表單過濾不顯示)。資安類表單可能很海量所以錯開。

**用戶腦中的 SOC 流程**(20 年的 SOC 經驗):
```
start
  → 依攻擊類型分支(branch by attack_type)的情報收集
  → 情報分析(統計學或 AI)
  → 人員簽核時有完整資訊
  → 人員離開系統做外部驗證/討論
  → 回系統簽處置流程(block/放行/誤判/升級 L2/L3)
  → end
```
用戶問「還有更好的方式嗎」。

---

## 我給用戶的建議(已認可,請依此實作)

### 方案 1:**分開頁面**,不要硬塞 /forms/center

原因:海量 + UI 形態完全不同(主視角從「申請人」變成「攻擊者 IP+嚴重度」,排序預設改嚴重度,需要 1-click 處置而非慢慢填表)。

**做法**:
- 新增 `/security-cases/` web blueprint(類比 form_workflow_web 的 center)
- **沿用 form_workflow 引擎與 model**(完全不動 fw_form_instances 等表)
- 用 `fw_categories` 分類隔離:加 `security` 分類,新中心 UI 用 `category=security` 過濾
- **原 /forms/center 加條件 `category != 'security'`**(把資安類過濾掉)
- 新中心顯示資安專屬欄位(嚴重度、攻擊者 IP、相關 decision、SLA 倒數)

### 方案 2:SOC 流程套用既有 form_workflow 節點 + 5 個現代化加強

| 用戶原本設計 | 用什麼節點 | 現代化加強 |
|---|---|---|
| 依攻擊類型分支 | `Branch` | 加 MITRE ATT&CK technique 自動標籤 |
| 情報收集 | `ParallelFork` + 多個自訂收集節點 + `ParallelJoin` | **改進 A:並行**(VirusTotal / ASN / 歷史案件 / BeakBroodNest 同時跑,各 30 秒 timeout) |
| 情報分析 | 自訂 handler 或 OpFieldWrite 寫 risk_score | **改進 B:risk_score + recommended_action + confidence**(規則或小型 ML),簽核者只看分數,信心高就 1-click |
| 人員簽核 | `FormAdapter` | **改進 C:SLA 計時器**,15 分鐘逾時自動升級 L2(Delay + Branch),L2 1 小時逾時 → L3 |
| 處置選擇 | `Branch` 後接多個 `SubFlow` | **改進 D:每個處置選項做成 SubFlow**(block / 放行 / 誤判 / 升級各自獨立,維護時不互相干擾) |
| End | `End` 前加 `OpFieldWrite` 或自訂節點 | **改進 E:結束回寫 BeakBroodNest 知識原子**(下次同 IP/TTP 進來時情報階段查得到歷史) |

**block 處置 SubFlow 內**:呼叫 `DecisionWriter` 節點(已上線)寫 `od_defense_decisions`,executor 自動拉走落地。**不要重做這層**。

### 方案 3:資安中心 UI 形態

主畫面參考 SIEM dashboard:
- **左側**:案件清單(嚴重度色塊、IP、攻擊類型、SLA 倒數)
- **右側**:選中案件的詳情(情報摘要 + risk_score + 處置按鈕)
- **頂部**:統計帶(待處理 / SLA 即將逾期 / 今日 block 數 / 失敗率)

頂部統計帶是 open_defense `/dashboard` 的擴充版,**重用 admin API 不要重做**。

---

## 實作建議的 ticket 拆解(估 4~5 張)

| Ticket | 內容 | 觸碰安全核心 |
|---|---|---|
| SOC-1 | `security` 分類 seed + 原 form center 過濾 | 否 |
| SOC-2 | 新 web blueprint `/security-cases/` + 案件列表頁 | 否 |
| SOC-3 | 案件詳情頁 + 處置按鈕(用既有 FormAdapter API) | 否 |
| SOC-4 | 5 個新節點 handler:**並行情報收集**範本(VT/ASN stub)、**risk_score 計算**、**SLA 計時觸發升級**、**知識庫回寫** | 否(form_workflow 內) |
| SOC-5 | SOC dashboard 擴充版(SLA / 失敗率 / 案件趨勢) | 否 |

每張完成 commit 一次,重啟 Flask dev server 驗證。

---

## 開工前必須與用戶確認的決策點

1. **risk_score 的演算法**:用簡單規則(severity*0.6 + repeat*0.4)還是接小型 ML 模型?(初期建議規則,等資料夠多再上 ML)
2. **SLA 時間**:L1 / L2 / L3 各幾分鐘?升級時通知誰?(LINE 群組 / Telegram / Email)
3. **情報來源**:封閉網路內哪些 API 可用?VirusTotal 線上版還是內網有 mirror?ASN/GeoIP 用 MaxMind 本機 DB?
4. **L2/L3 是同一套表單流程還是另開?**(建議同一套,用 status 欄位區分階段,以利串連完整 timeline)
5. **誤判標記要回送 detector 嗎?**(若要,要在 sec-vm bridge 端加一條反向通道,屬契約 v2)

---

## 環境資訊速查

- 專案根目錄:`/opt/BeakPlatform-dev`
- DB:`postgresql://beakplatform:postgres123@localhost/beakplatform_dev`
- Flask dev server:`flask run --host=127.0.0.1 --port=7000`(URL 加 `/beakplatform` 前綴)
- 對外 LAN URL:`http://192.168.0.16:7000/beakplatform/`
- 測試 org:beluga `_9c8TewkRkCBEf3XsUdqeF`(管理員 admin-ethanyu@beluga.com)
- sec-vm:`192.168.0.20`(對方 Claude 在管,溝通時用本對話建立的 IK/SA 憑證)
- BeakBroodNest 知識庫:`mcp__beak_broodnest__note_*` MCP tools 可用,**取代 MEMORY.md**
- 相關知識原子 ID:4241(open_defense 總覽)、4242(datetime 時區陷阱)、4243(模組合約啟用陷阱)

## 開工順序

1. 跟用戶確認上述 5 個決策點
2. 認可後寫 manifest `docs/manifests/mod-security-case-center.yaml` 並登錄 README.yaml
3. 從 SOC-1 開始一張一張做,每張完成 commit 並重啟 dev server 驗證
4. 完成後寫 `docs/security_case_center_quickstart.md`(類比 open_defense_quickstart.md 風格)

---

## 不要做的事

- **不要改** `docs/integrations/open_defense_contract.md`(對外契約凍結)
- **不要重做** `od_defense_decisions` 寫入機制(用既有 `DecisionWriter` 節點)
- **不要重做** SA / IK 管理(沿用 open_defense UI)
- **不要在** `/forms/center` 加 if/else 處理資安特殊邏輯(分開新頁面)
- **不要繞過** 既有 form_workflow 引擎自己刻一套(會分裂維護)
- 修改安全核心檔案(`backend/app/security/*`)前要再確認,本次 OpenDefense 的擴充已用一次性授權,**這次需要重新確認**

祝順利。
