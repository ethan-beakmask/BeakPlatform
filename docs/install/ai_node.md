# AI 分析節點（AiAgent）的部署需求

**這是選用功能。** 流程設計器裡的「AI 分析」節點會呼叫**本機安裝的
Claude Code CLI** 來分析流程資料，把判定結果寫進流程變數並可插入一筆簽核註記。
沒有用到這個節點的話，本頁整份可以略過，平台其餘功能不受影響。

這份文件寫給**安裝與維運人員**，不需要平台在執行中就能閱讀。

---

## 一、先確認四件事

| 需求 | 說明 |
|---|---|
| 已安裝 Claude Code CLI | 版本必須支援 `--safe-mode` 與 `--tools` 兩個參數（見下方「版本」） |
| 執行流程的 OS 帳號已完成登入 | CLI 的認證資料存在該帳號的 `$HOME/.claude/`，**必須先以互動方式登入過一次** |
| 該帳號的家目錄可寫 | CLI 啟動時會在家目錄建立自己的設定與快取檔 |
| 主機可連外 | CLI 需要連線到模型服務。完全封閉的網路請見「內部代理與私有端點」 |

**不需要**為這個節點建立任何目錄。每次執行時平台會自動建立一個臨時空目錄當工作目錄，
用完即刪。

### 版本

節點一律以下列兩個參數執行 CLI，用意是關閉所有自訂設定與所有工具：

```
--safe-mode      停用全部自訂（設定檔、外掛、掛載的外部工具伺服器等）
--tools ""       停用全部內建工具
```

**這兩個參數不可停用，也沒有任何設定可以略過。** 節點分析的內容通常來自外部
（例如 HTTP 請求原文），必須假設它含有惡意指令。

舊版 CLI 沒有 `--safe-mode`。平台在執行前會自動偵測，缺少參數時**直接失敗、
不會退化成沒有隔離的執行方式**。偵測是看 CLI 自己的 `--help` 輸出，
不是比對版本號，所以升級後不需要修改任何設定。

---

## 二、指定 CLI 路徑：`AI_NODE_CLI_PATH`

平台尋找 CLI 的順序是：

1. `.env` 的 `AI_NODE_CLI_PATH`
2. `PATH` 上的 `claude`
3. 字面 `claude`（交給系統解析）

**強烈建議直接填絕對路徑。** 流程節點由背景服務執行，而 systemd 服務的 `PATH`
與你在終端機裡的 `PATH` 不同——常見情況是 CLI 裝在使用者家目錄的
`~/.local/bin`，而服務的 `PATH` 不含這個目錄，於是服務找到的是另一份舊版 CLI，
或是根本找不到。

```bash
# 先確認實際路徑與版本
which claude
claude --version

# 寫進 <安裝目錄>/.env
AI_NODE_CLI_PATH=/絕對路徑/claude
```

改完 `.env` 後要重新啟動流程執行服務才會生效。

---

## 三、認證資料放在誰的家目錄

節點的實際執行者是**流程執行器**，不是網頁服務。認證資料要放在**執行器所屬 OS
帳號**的家目錄底下。兩種部署形態的執行者不同：

| 部署形態 | 判別方式 | 認證要放哪 |
|---|---|---|
| 獨立執行器服務 | `.env` 或服務設定有 `EXECUTOR_STANDALONE=1` | 該 systemd 服務 `User=` 指定帳號的家目錄 |
| 網頁服務內建執行器 | 沒有設定 `EXECUTOR_STANDALONE` | 網頁服務所屬帳號的家目錄 |

確認方式：

```bash
# 以執行器帳號的身分執行，應該要能正常回應
sudo -u <執行器帳號> -H claude -p --output-format json --model <模型> \
  --safe-mode --tools "" <<< "說 ok"
```

回應中出現 `Not logged in` 就是還沒登入。請以該帳號登入一次
（需要可互動的終端機）：

```bash
sudo -u <執行器帳號> -H claude
```

若該帳號被設定為不可登入（例如 `nologin`），可改用下一節的 API 金鑰方式，
不必為此開放互動登入。

---

## 四、可用的認證方式與環境變數

節點執行 CLI 時**不會繼承整份環境變數**——平台的資料庫連線字串、加密金鑰等
機密刻意不會傳給子行程。傳入的只有下表這些：

| 變數 | 何時需要 |
|---|---|
| `HOME`、`PATH`、`LANG` | 一律傳入 |
| `ANTHROPIC_*` | 以 API 金鑰認證，或指向自架的相容端點 |
| `CLAUDE_CODE_USE_BEDROCK`、`CLAUDE_CODE_USE_VERTEX` | 改用雲端供應商的模型服務 |
| `AWS_*` | **僅在** `CLAUDE_CODE_USE_BEDROCK` 啟用時傳入 |
| `GOOGLE_APPLICATION_CREDENTIALS`、`GOOGLE_CLOUD_PROJECT`、`CLOUD_ML_REGION` | **僅在** `CLAUDE_CODE_USE_VERTEX` 啟用時傳入 |
| `HTTP_PROXY`、`HTTPS_PROXY`、`NO_PROXY`（含小寫形式） | 需要經由代理伺服器連外 |
| `NODE_EXTRA_CA_CERTS`、`SSL_CERT_FILE`、`SSL_CERT_DIR` | 內部憑證頒發機構簽發的 TLS 憑證 |

**這些變數要設在執行器行程的環境裡**（systemd 的 `Environment=` 或
`EnvironmentFile=`），不是設在你的登入 shell 裡。

### 內部代理與私有端點

出網需經代理，或改打內部的相容端點時：

```ini
# /etc/systemd/system/<執行器服務>.service.d/ai-node.conf
[Service]
Environment=HTTPS_PROXY=http://proxy.internal:8080
Environment=NO_PROXY=localhost,127.0.0.1
Environment=NODE_EXTRA_CA_CERTS=/etc/ssl/certs/internal-ca.pem
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart <執行器服務>
```

完全無法連外的環境無法使用這個節點，流程請改走純規則判斷的節點。

---

## 五、systemd 設定範例

重點只有兩個：`PATH` 不可靠所以填絕對路徑；家目錄必須可讀寫。

```ini
[Service]
User=<執行器帳號>
Group=<執行器群組>
EnvironmentFile=<安裝目錄>/.env
# 認證存在家目錄，因此不可使用 ProtectHome / DynamicUser
# ProtectHome=yes        <- 會讓節點無法認證
# DynamicUser=yes        <- 同上，且每次啟動帳號都不同
```

服務若已套用 `PrivateTmp=yes` 沒有問題——節點的臨時工作目錄跟著隔離，行為正常。

---

## 六、錯誤訊息對照

節點失敗時，訊息會出現在流程的節點執行紀錄裡。

| 訊息 | 意義 | 處置 |
|---|---|---|
| `AI CLI 找不到執行檔: ...` | 服務的 `PATH` 找不到 CLI | 設定 `AI_NODE_CLI_PATH` 為絕對路徑 |
| `AI CLI 版本過舊或不支援隔離參數 --safe-mode / --tools` | CLI 太舊 | 升級 CLI；升級後不必改設定，但要重啟服務讓它重新偵測 |
| `AI CLI 退出碼 1，原因 ...: Not logged in · Please run /login` | 執行器帳號沒有認證資料 | 見第三節 |
| `AI CLI 逾時（N s）` | 分析超過節點設定的秒數 | 調高節點的逾時設定，或縮小送進去的內容 |
| `AI 輸出未通過 canary/schema 驗證，已作廢` | 回應不符合預期格式，可能遭注入影響 | 這是**保護機制正常運作**。節點依設定走錯誤路徑，不會採信該次輸出 |
| `AI CLI 無法執行: ...` | 檔案權限不足 | 確認執行器帳號對該檔案有執行權 |

診斷時可直接以執行器帳號重現（見第三節的指令），比看流程紀錄快。

---

## 七、費用與用量歸屬

- 所有企業的流程共用**同一份主機端認證**，用量與費用歸屬於該帳號，
  平台目前不提供逐企業的用量統計或配額。
- 請自行確認所使用的方案條款允許這種伺服器端的自動化用法。
- 節點每次執行都是一次獨立的模型呼叫。流程若會大量觸發，
  建議在 AI 節點之前先用條件判斷節點過濾掉不需要分析的案件。

---

## 八、這個節點的安全邊界（維運人員須知）

- **AI 沒有任何寫入權限。** 它只輸出文字，所有寫入（流程變數、簽核註記）
  都由平台在取得輸出之後自己執行。
- **規則層偵測不經過 AI。** 平台自己會掃描注入特徵，結果直接生效；
  規則命中而 AI 判定無害時會強制升級，並在註記開頭加上系統警示，
  該警示是平台在 AI 輸出之後拼接的，AI 無法移除。
- **CLI 路徑不可由流程設定指定。** 流程定義可被有編輯權的人修改，
  若允許在節點裡指定執行檔，等同讓對方以執行器帳號執行任意程式。
  路徑只接受來自 `.env` 的設定。
- 節點分析的內容視為不可信資料，一律包在隨機邊界標記內送出。
