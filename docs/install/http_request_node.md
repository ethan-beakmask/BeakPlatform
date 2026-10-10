# 「HTTP 呼叫」節點的部署需求

適用對象：平台系統管理員、主機管理員。

「HTTP 呼叫」（`HttpRequest`）讓流程對外送出 HTTP(S) 請求。這是企業級節點，
不需要節點授權；安全邊界由目的地白名單控制，而且白名單採 fail-closed：
沒有設定或設定空清單時，任何目的地都會被拒絕。

---

## 一、白名單設定

兩個系統設定都是 JSON：

| key | 型別 | 說明 |
|---|---|---|
| `http_request_allowed_hosts` | list | 全平台允許目的地。空清單或不存在代表全部拒絕 |
| `http_request_org_allowed_hosts` | object | 企業專屬限制；有列出的企業必須同時通過平台清單與企業清單 |

範例（在平台安裝目錄執行；`SystemSetting.set()` 會自動建立或更新該筆設定，
直接對 `system_settings` 下 `UPDATE` 在設定尚不存在時不會有任何效果）：

```bash
cd <安裝目錄> && set -a && source .env && set +a && cd backend && ../venv/bin/flask shell <<'PY'
from app.models import SystemSetting
SystemSetting.set('http_request_allowed_hosts',
                  ['api.example.com', '*.partner.example', '192.168.0.112:8443'],
                  value_type='json', category='http_request',
                  description='HttpRequest 節點允許的目的地')
SystemSetting.set('http_request_org_allowed_hosts',
                  {'<企業識別碼>': ['api.example.com']},
                  value_type='json', category='http_request',
                  description='HttpRequest 節點各企業允許的目的地')
PY
```

改完不必重啟服務，節點每次執行都會重新讀取設定。

清單項目支援：

| 寫法 | 意思 |
|---|---|
| `api.example.com` | 這個主機名，任何埠 |
| `api.example.com:8443` | 這個主機名，只限指定埠 |
| `*.example.com` | 一層以上子網域，不含 `example.com` 本身 |
| `203.0.113.10`、`203.0.113.0/24` | IP 或 CIDR，任何埠；也可加 `:埠` |

## 二、SSRF 防護規則

節點會先解析 URL 主機名，再用白名單比對主機名與解析出的 IP。若解析出的任一 IP
是 private、loopback、link-local、multicast、reserved 或 unspecified，必須落在
某個 IP／CIDR 白名單項目內才會放行。

也就是說，`*.example.com` 解析到內網 IP 時仍會被拒絕；內網目的地請明確寫成
`192.168.0.112` 或 `192.168.0.0/24` 這類 IP／CIDR。

已知限制：DNS 解析與實際連線之間仍有很短的時間差，本節點不做連線層 IP 釘選。
高敏感環境建議白名單只寫 IP／CIDR，不寫主機名。

## 三、設計者必知

- 節點不跟隨 redirect，3xx 會記為 `http_error`
- 節點不因 HTTP 失敗自動重試；請用分支節點判斷 `<前綴>_ok`
- 不要把 API key 放在 URL query string，`<前綴>_url` 會記錄實際呼叫網址
- 本版沒有秘密儲存；標頭值存在流程圖裡，能編輯流程的人都看得到

## 四、與等待外部回呼節點搭配時要先設系統對外網址

若 HTTP 呼叫內容會帶 `${cb.<等待節點 ID>}`，平台會用 `system_base_url` 組出外部系統可打回來的完整網址。
請先到主機設定填「系統對外網址」，或用既有維運方式建立 `system_base_url`。未設定時回呼網址會是空字串，
外部系統收不到可用的 callback URL。
