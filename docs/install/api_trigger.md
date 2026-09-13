# 用指令建一張資安案件單

這條路徑給外部系統或讀者手動驗證用：用 API Key 呼叫平台的外部表單觸發閘道，直接建立一張資安案件單。

## 一、在示範企業建立 API Key

用示範企業的管理員或具備安全中心權限的帳號登入：

```text
http://<平台IP>:<埠>/beakplatform/security/api-keys/
```

新增 API Key 時，授權範圍選資安分類可用的表單觸發範圍。建立完成後，畫面會顯示 `key_id` 與 `secret`。

`secret` 只顯示一次，請立即保存。它是 base64url 字串；`bp_trigger.py` 會自己解碼成 HMAC 使用的 raw bytes，不要自行轉碼。

## 二、列出可觸發的表單

建議把認證放在環境變數，避免 secret 留在 shell history：

```bash
export BP_BASE_URL='http://<平台IP>:<埠>/beakplatform'
export BP_KEY_ID='ak_xxxxxxxx'
export BP_SECRET='<建立 API Key 時顯示一次的 secret>'

python3 scripts/bp_trigger.py --list
```

輸出會列出這把 key 可用的表單與每張表單的 `field_keys`。示範企業的資安案件表單 `form_code` 是 `SEC_INCIDENT_RESPONSE`（另有 SOC 團隊版 `SEC_IR_SOC_TEAM`、單人版 `SEC_IR_SOLO`），欄位名以 `field_keys` 為準。

## 三、建立一張案件

```bash
python3 scripts/bp_trigger.py \
  --form-code SEC_INCIDENT_RESPONSE \
  --subject 'TEST-手動 API 建單' \
  --field finding_title='TEST-手動建單' \
  --field source_system=manual \
  --field severity_id=3 \
  --field actor_ip=203.0.113.42 \
  --field target_host=demo.internal
```

也可以用 `--json` 給整包 `form_data`，再用 `--field` 覆蓋或追加單一欄位：

```bash
python3 scripts/bp_trigger.py \
  --form-code SEC_INCIDENT_RESPONSE \
  --subject 'TEST-弱點通報' \
  --json '{"finding_title":"TEST-弱點通報","source_system":"manual","severity_id":3}' \
  --field actor_ip=203.0.113.42
```

成功時平台會回傳建立結果。接著回到 UI 的「表單中心」或「開放防禦 / 資安案件處置中心」查看標題含 `TEST-` 的案件。

## 四、錯誤碼對照

| HTTP | code | 常見原因 |
|---|---|---|
| 400 | `invalid_json` | request body 不是合法 JSON |
| 400 | `missing_form_identifier` | 沒有提供 `form_code` 或已發行表單識別 |
| 400 | `missing_subject` | 缺少 `subject` |
| 400 | `form_data_must_be_object` | `form_data` 不是 JSON 物件 |
| 400 | `unknown_field` | 欄位名稱不在表單內；回應會附 `allowed_keys` |
| 401 | `auth_failed` | key id、secret、簽章或時間戳錯誤 |
| 403 | `scope_denied` | API Key 沒有這個觸發範圍 |
| 404 | `form_not_found` | 找不到表單，或表單不在這把 key 可見範圍 |
| 422 | `form_not_published` | 表單尚未發行 |

## 五、自我測試

```bash
python3 scripts/bp_trigger.py --selftest <form_code>
```

自我測試會驗證四項行為：列出表單、未知欄位、不存在或 scope 外表單、錯誤簽章。這不會替你判斷業務欄位是否填得完整，只用來確認 API Key 與簽章路徑正常。
