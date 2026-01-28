# BeakPlatform E-MailRelay

系統級郵件中繼服務，用於發送系統通知郵件。

## 目錄結構

```
E-MailRelay/
├── emailrelay.conf          # 主要配置檔
├── emailrelay.auth          # 認證檔（需自行建立，不上傳 Git）
├── emailrelay.auth.example  # 認證檔範例
├── spool/                   # 郵件暫存目錄
├── logs/                    # 日誌目錄
└── README.md                # 本文件
```

## 安裝步驟

### 1. 安裝 E-MailRelay

```bash
# Ubuntu 24.04
cd /opt/BeakPlatform
wget "https://sourceforge.net/projects/emailrelay/files/emailrelay/2.6/emailrelay_2.6_amd64-ub2404.deb/download" -O emailrelay.deb
sudo dpkg -i emailrelay.deb
rm emailrelay.deb

# 其他版本請至 SourceForge 下載
```

### 2. 設定目錄權限

```bash
# 設定目錄擁有者（改為你的用戶）
sudo chown -R $(whoami):$(whoami) /opt/BeakPlatform/E-MailRelay
chmod 700 /opt/BeakPlatform/E-MailRelay
```

### 3. 設定 SMTP 認證

**方法一：使用系統設定頁面（推薦）**

登入 BeakPlatform 後，進入「系統設定 > E-MailRelay」頁面設定。

**方法二：手動建立認證檔**

```bash
# Gmail 應用程式密碼（有空格）需要 Base64 編碼
EMAIL_B64=$(echo -n "your.email@gmail.com" | base64)
PASSWORD_B64=$(echo -n "xxxx xxxx xxxx xxxx" | base64)

echo "client plain:b $EMAIL_B64 $PASSWORD_B64" > emailrelay.auth
chmod 600 emailrelay.auth
```

### 4. 安裝 systemd 服務

```bash
sudo cp /opt/BeakPlatform/E-MailRelay/beakplatform-emailrelay.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable beakplatform-emailrelay
sudo systemctl start beakplatform-emailrelay
```

## 服務管理

```bash
# 查看狀態
sudo systemctl status beakplatform-emailrelay

# 啟動/停止/重新啟動
sudo systemctl start beakplatform-emailrelay
sudo systemctl stop beakplatform-emailrelay
sudo systemctl restart beakplatform-emailrelay

# 查看日誌
tail -f /opt/BeakPlatform/E-MailRelay/logs/emailrelay-$(date +%Y%m%d).log
```

## 故障排除

### 郵件沒有發送

1. 檢查服務狀態
2. 檢查 spool 目錄是否有郵件
3. 檢查日誌

### 認證失敗 (too many fields)

原因：密碼中有空格被當成欄位分隔符

解決：使用 `plain:b` 格式（Base64 編碼）

### 認證失敗 (authentication failed)

1. Gmail 需要使用「應用程式密碼」，不是帳號密碼
2. 確認 Base64 編碼正確

## Gmail 應用程式密碼申請

1. 登入 Gmail
2. 前往 https://myaccount.google.com/apppasswords
3. 選擇應用程式 > 其他 > 輸入「BeakPlatform」
4. 點選「產生」
5. 複製 16 字元密碼（格式如 xxxx xxxx xxxx xxxx）
