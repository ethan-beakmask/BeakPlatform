# E-MailRelay 安裝與設定指南

BeakMask 使用 E-MailRelay 作為系統郵件中繼服務，負責發送密碼重設驗證信、系統通知等郵件。

E-MailRelay 是一個獨立的開源 SMTP store-and-forward 伺服器（GPL v3 授權），BeakMask 不包含也不修改其原始碼，僅透過設定檔與命令列工具整合。

---

## 運作原理

```
BeakMask --> emailrelay-submit --> spool/ --> emailrelay daemon --> Gmail SMTP
```

1. BeakMask 呼叫 `emailrelay-submit` 將郵件寫入 spool 目錄
2. E-MailRelay daemon 定期掃描 spool，透過 TLS 轉發至外部 SMTP（如 Gmail）
3. E-MailRelay 不啟動 SMTP 監聽，僅作為發送端

---

## 方式一：自動安裝（推薦）

BeakMask 提供安裝腳本，可自動完成所有步驟。

### 前置需求

- Ubuntu 22.04 / 24.04（其他 Linux 發行版需自行調整）
- 編譯安裝需要：`build-essential`、`libssl-dev`
- 複製安裝需要：一個現有的 E-MailRelay 安裝目錄

### 使用方式

```bash
cd /opt/BeakPlatform/scripts

# 方式 A：從網路下載原始碼編譯安裝
./install_emailrelay.sh --prefix /opt/E-MailRelay --download

# 方式 B：從本機原始碼壓縮檔編譯
./install_emailrelay.sh --prefix /opt/E-MailRelay --source /path/to/emailrelay-2.6-src.tar.gz

# 方式 C：從現有安裝複製二進位檔（最快，適合同架構機器間複製）
./install_emailrelay.sh --prefix /opt/E-MailRelay --copy-from /path/to/existing/install
```

### 參數說明

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `--prefix DIR` | 安裝目錄（必填） | - |
| `--download` | 從 SourceForge 下載原始碼 | - |
| `--source FILE` | 指定本機原始碼壓縮檔 | - |
| `--copy-from DIR` | 從現有安裝複製 | - |
| `--smtp-server HOST` | SMTP 轉發伺服器 | smtp.gmail.com:587 |
| `--user USER` | 服務執行帳號 | 目前使用者 |
| `--no-service` | 不建立 systemd service | - |

### 安裝後設定

1. 啟動服務：`sudo systemctl start emailrelay`
2. 進入 BeakMask 管理介面 > 主機設定 > 伺服器設定 > E-MailRelay
3. 設定「安裝路徑」為安裝腳本的 `--prefix` 值
4. 設定 SMTP 認證（Gmail 帳號 + 應用程式密碼）
5. 點擊「發送測試郵件」確認

---

## 方式二：手動安裝

### Step 1：取得 E-MailRelay

從官方網站下載：https://sourceforge.net/projects/emailrelay/

```bash
# 下載原始碼
wget https://sourceforge.net/projects/emailrelay/files/emailrelay/2.6/emailrelay-2.6-src.tar.gz/download -O emailrelay-2.6-src.tar.gz

# 安裝編譯工具
sudo apt-get update
sudo apt-get install -y build-essential libssl-dev

# 解壓、編譯、安裝
tar -xzf emailrelay-2.6-src.tar.gz
cd emailrelay-2.6
./configure --prefix=/opt/E-MailRelay
make -j$(nproc)
sudo make install
```

### Step 2：建立目錄結構

```bash
INSTALL_DIR=/opt/E-MailRelay   # 改為你的安裝路徑
YOUR_USER=$(whoami)

sudo mkdir -p "$INSTALL_DIR"/{spool,logs,etc}
sudo chown -R "$YOUR_USER":"$YOUR_USER" "$INSTALL_DIR"
chmod 755 "$INSTALL_DIR"/spool
chmod 755 "$INSTALL_DIR"/logs
```

### Step 3：建立設定檔

建立 `$INSTALL_DIR/etc/emailrelay.conf`：

```
# E-MailRelay Configuration

# Spool 目錄
spool-dir /opt/E-MailRelay/spool

# 定期檢查 spool 目錄（秒）
poll 10

# 目標 SMTP 伺服器（Gmail）
forward-to smtp.gmail.com:587

# 啟用 TLS 加密
client-tls

# SMTP 認證檔案
client-auth /opt/E-MailRelay/etc/emailrelay.auth

# 日誌設定
log-file /opt/E-MailRelay/logs/emailrelay-%d.log

# 不啟動 SMTP 監聽（使用 emailrelay-submit 提交）
no-smtp
```

注意：將設定檔中的 `/opt/E-MailRelay` 替換為你的實際安裝路徑。

### Step 4：建立認證檔

SMTP 認證可透過 BeakMask Web UI 設定，或手動建立：

```bash
# 將 email 和密碼 Base64 編碼
EMAIL_B64=$(echo -n "your.email@gmail.com" | base64)
PASS_B64=$(echo -n "xxxx xxxx xxxx xxxx" | base64)

# 寫入 auth 檔案
echo "client plain:b $EMAIL_B64 $PASS_B64" > "$INSTALL_DIR/etc/emailrelay.auth"
chmod 600 "$INSTALL_DIR/etc/emailrelay.auth"
```

Gmail 應用程式密碼取得方式：
1. 登入 Google 帳號
2. 前往 https://myaccount.google.com/apppasswords
3. 選擇「郵件」和「其他」，命名後產生 16 碼密碼

### Step 5：建立 systemd service

建立 `/etc/systemd/system/emailrelay.service`：

```ini
[Unit]
Description=E-MailRelay
After=network-online.target
Wants=network-online.target

[Service]
Type=forking
Restart=on-failure
RestartSec=10
User=YOUR_USER
Group=YOUR_USER
WorkingDirectory=/opt/E-MailRelay
ExecStart=/opt/E-MailRelay/sbin/emailrelay --as-server --pid-file /opt/E-MailRelay/emailrelay.pid /opt/E-MailRelay/etc/emailrelay.conf
ExecStop=/bin/kill -15 $MAINPID
PIDFile=/opt/E-MailRelay/emailrelay.pid

[Install]
WantedBy=multi-user.target
```

替換 `YOUR_USER` 和所有路徑為你的實際值。

```bash
sudo systemctl daemon-reload
sudo systemctl enable emailrelay
sudo systemctl start emailrelay
```

### Step 6：設定 BeakMask

1. 登入 BeakMask 系統管理員帳號
2. 前往「主機設定」>「伺服器設定」
3. 在 E-MailRelay 區塊：
   - 設定「安裝路徑」為你的安裝目錄（如 `/opt/E-MailRelay`）
   - 設定 SMTP 認證（若 Step 4 已手動設定則此處會自動載入）
   - 設定發件人名稱和 Email
4. 點擊「發送測試郵件」確認收到

---

## 驗證安裝

### 檢查服務狀態

```bash
sudo systemctl status emailrelay
```

### 手動測試發信

```bash
INSTALL_DIR=/opt/E-MailRelay   # 改為你的安裝路徑

echo -e "From: test@beakmask.local\nTo: your@email.com\nSubject: Test\n\nHello" \
  | "$INSTALL_DIR/sbin/emailrelay-submit" \
    --from test@beakmask.local \
    -s "$INSTALL_DIR/spool" \
    your@email.com
```

郵件會進入 spool 目錄，daemon 會在下一個 poll 週期（預設 10 秒）自動轉發。

### 檢查日誌

```bash
tail -f "$INSTALL_DIR/logs/emailrelay-$(date +%Y%m%d).log"
```

成功轉發時會顯示類似：
```
emailrelay: info: smtp connection to 108.177.125.108:587
```

---

## 疑難排解

### 郵件停留在 spool 不轉發

1. 確認 daemon 正在運行：`systemctl status emailrelay`
2. 檢查 auth 檔案權限：`ls -la $INSTALL_DIR/etc/emailrelay.auth`（應為 600）
3. 檢查日誌是否有認證錯誤

### Gmail 認證失敗

1. 確認使用的是「應用程式密碼」而非帳號密碼
2. 確認 Gmail 帳號已啟用兩步驟驗證
3. 應用程式密碼格式為 16 碼（如 `xxxx xxxx xxxx xxxx`）

### BeakMask 顯示「emailrelay-submit not found」

1. 確認安裝路徑設定正確（主機設定 > E-MailRelay > 安裝路徑）
2. 確認二進位檔存在：`ls -la $INSTALL_DIR/sbin/emailrelay-submit`
3. 確認 BeakMask 執行帳號有權限存取該路徑

---

## 授權資訊

E-MailRelay 採用 GNU General Public License v3 授權。
作者：Graeme Walker
官方網站：https://emailrelay.sourceforge.net/
