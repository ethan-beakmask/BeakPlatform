# 外部身份來源整合規劃

> 狀態：**Deferred** — 已完成初步設計討論，未進入開發。
> 建立日期：2026-02-07
> 現況註記（2026-07-07）：已落地的前置基礎僅 `users.external_identity` 欄位
> （migration `scripts/migrations/legacy/068_user_external_identity.py`，同企業內唯一，
> 作為 AD UPN 跨站識別錨點）。OIDC/LDAP 登入、`OrgIdentityConfig`、
> `auth_source` 均尚未實作。後續 SSO/AD 整合待建 Samba AD DC 測試環境。

---

## 一、產業現況：主流企業帳號管理系統

| 類型 | 名稱 | 說明 |
|------|------|------|
| 地端目錄 | Windows AD (AD DS) | 企業地端霸主 |
| 地端目錄 | LDAP / OpenLDAP | AD 的底層協議，Linux/Unix 環境廣泛使用 |
| 雲端 IdP | Microsoft Entra ID (Azure AD) | 雲端版 AD，綁 M365，企業雲端化首選 |
| 雲端 IdP | Google Workspace | 教育機構、新創公司大量採用 |
| 雲端 IdP | Okta (含 Auth0) | 北美企業市佔最高的獨立 IdP |
| 開源 IdP | Keycloak | Red Hat 出品，自建 IdP 的首選，採用量很大 |

## 二、對接協議

| 協議 | 用途 | 誰在用 |
|------|------|--------|
| SAML 2.0 | SSO 聯邦登入 | 傳統企業標配，幾乎所有 IdP 都支援 |
| OIDC (OpenID Connect) | 現代 SSO | OAuth 2.0 之上，Google/Entra ID/Keycloak/Okta 都走這個 |
| LDAP | 目錄查詢/認證 | AD、OpenLDAP 直連 |
| SCIM | 帳號自動同步 (provisioning) | Okta/Entra ID 推帳號到應用系統用 |

## 三、BeakPlatform 開發優先順序

支援 OIDC + LDAP 覆蓋 90% 以上場景：

1. **OIDC** — 一個協議打通 Google、Entra ID、Keycloak、Okta（雲端）
2. **LDAP** — 打通地端 AD 和 OpenLDAP（地端）
3. SAML 2.0 — 視需求再議（傳統企業有些只願意開 SAML）

## 四、設計決策（已確認）

### 4.1 帳號來源模式

每個企業建立時**擇一**，事後不處理切換/合併：

- **本地帳號 (Local)** — 目前已實作，管理員手動建帳
- **OIDC** — 透過外部 IdP 認證（未來）
- **LDAP** — 透過地端目錄認證（未來）

### 4.2 登入共存（未定案）

OIDC/LDAP 企業是否同時保留本地密碼登入？待定。
可能場景：系統管理員帳號需要本地密碼作為 fallback。

### 4.3 IdP 設定方式

**方案 B：每個企業各自設定自己的 IdP。**

企業管理員在企業設定中配置：
- IdP 類型 (OIDC / LDAP)
- OIDC: issuer URL、client_id、client_secret、scopes
- LDAP: server URL、bind DN、base DN、filter

### 4.4 首次登入行為

- OIDC/LDAP 用戶首次登入時**自動建帳**
- 透過 **email 比對**確認所屬企業（email domain → organization.domain_name）
- 本系統必填欄位（english_name、native_name、username）從 IdP claims 複製：
  - `email` → username（@ 前面部分）
  - `name` / `given_name` + `family_name` → english_name、native_name
  - 缺少的欄位用 email 的 username 部分填充
- display_name 依企業設定自動衍生（與本地建帳邏輯一致）

### 4.5 既有帳號合併

**不處理。** 企業從一開始就只能選擇一種帳號來源。
不存在「先用本地，後來改 OIDC」的遷移場景。

## 五、驗證環境規劃

- **OIDC 測試**：本機 Docker 跑 Keycloak，建 realm + 測試用戶
- **LDAP 測試**：本機 Docker 跑 OpenLDAP
- 不需要外部雲端服務即可完整驗證

## 六、技術備註

- Python OIDC 套件推薦：Authlib
- Python LDAP 套件推薦：python-ldap 或 ldap3
- 需要在 Organization model 新增 `auth_source` 欄位（local / oidc / ldap）
- 需要新增 `OrgIdentityConfig` model 儲存 IdP 連線設定
- 登入流程需要在 auth 模組中分支：根據 email domain 判斷走本地驗證還是外部 IdP
