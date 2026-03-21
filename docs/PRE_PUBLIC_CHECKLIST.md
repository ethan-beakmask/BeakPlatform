# BeakPlatform 公開前檢查項目

本文件列出將 GitHub repository 從 private 轉為 public 之前，必須完成的所有檢查項目。

---

## 1. Git 歷史清理

GitHub 的 git history 中可能殘留敏感檔案的舊版本。公開前必須用 `git filter-repo` 清除。

**上次執行日期**: 2026-03-22

### 執行步驟

```bash
# 1. 在暫存目錄 clone GitHub repo
cd /tmp
git clone git@github.com-beakplatform:beakplatform/BeakPlatform.git beakplatform-github-clean
cd beakplatform-github-clean

# 2. 執行 filter-repo 移除所有敏感路徑
git filter-repo \
  --path docs/ --path tools/ --path devtools/ --path .forgejo/ \
  --path scripts/migrations/ --path scripts/systemd/ \
  --path backend/app/templates/pages/dev/ \
  --path CLAUDE.md \
  --path beakplatform.service \
  --path restart_flask.sh \
  --path deploy/.env.production \
  --path deploy/setup-remote-host.sh \
  --path deploy/setup-ssh-deploy-key.sh \
  --path deploy/deploy-remote.sh \
  --path scripts/push_github.sh \
  --path scripts/init_database.sh \
  --path scripts/install.sh \
  --path scripts/seed_data.py \
  --path scripts/seed_test_companies.py \
  --path scripts/analyze_project.py \
  --path scripts/install_emailrelay.sh \
  --path scripts/backfill_sync.py \
  --path scripts/sync_worker.py \
  --path scripts/beakplatform-sync-worker.service \
  --path scripts/migrate_variable_syntax.py \
  --path scripts/upgrade_approval_tables.py \
  --path scripts/rotate_credentials.py \
  --path scripts/sql_form_setup.sql \
  --path scripts/readme.txt \
  --path scripts/security_scan.sh \
  --path scripts/spec_check.py \
  --path scripts/add_column_comments.sql \
  --path scripts/init_db.sql \
  --path scripts/verify_install.sh \
  --path backend/app/web/dev.py \
  --path backend/app/static/js/quick-login.js \
  --invert-paths --force

# 3. 驗證敏感檔案已從所有歷史中移除
git rev-list --all --objects | git cat-file --batch-check='%(objecttype) %(objectname) %(rest)' | grep -E '(\.env\.production|CLAUDE\.md|seed_data\.py|admin123)'
# 預期: 無輸出

# 4. Force push
git remote add origin git@github.com-beakplatform:beakplatform/BeakPlatform.git
git push origin main --force

# 5. 清理
cd /tmp && rm -rf beakplatform-github-clean
```

---

## 2. 推送排除清單確認

確認 `scripts/push_github.sh` 的排除清單是最新的。

```bash
# 用更新後的排除清單推一次
cd /opt/BeakPlatform
bash scripts/push_github.sh
```

### 不可出去的目錄
| 目錄 | 原因 |
|------|------|
| `docs/` | 內部文件，公開前需逐一審查放行 |
| `tools/` | 內部工具 |
| `devtools/` | 開發工具 |
| `.forgejo/` | CI 設定 (Forgejo 專用) |
| `scripts/migrations/` | 資料庫遷移腳本 |
| `scripts/systemd/` | systemd 服務設定 |
| `backend/app/templates/pages/dev/` | 開發頁面 |

### 不可出去的檔案
| 檔案 | 原因 |
|------|------|
| `CLAUDE.md` | AI 協作設定，含內部架構資訊 |
| `deploy/.env.production` | 環境變數範本含密碼佔位 |
| `deploy/setup-remote-host.sh` | 內部部署腳本 |
| `deploy/setup-ssh-deploy-key.sh` | SSH key 部署 |
| `deploy/deploy-remote.sh` | 遠端部署腳本 |
| `scripts/push_github.sh` | 過濾推送腳本本身 |
| `scripts/init_database.sh` | DB 初始化 |
| `scripts/install.sh` | 安裝腳本 |
| `scripts/seed_data.py` | 測試種子資料 (含預設密碼) |
| `scripts/seed_test_companies.py` | 測試企業資料 |
| `scripts/rotate_credentials.py` | 憑證輪換 |
| `scripts/security_scan.sh` | 安全掃描 |
| 其他 scripts/* | 見 push_github.sh 完整清單 |
| `backend/app/web/dev.py` | 開發快捷登入 |
| `backend/app/static/js/quick-login.js` | 開發快捷登入 JS |
| `beakplatform.service` | systemd 服務設定 |
| `restart_flask.sh` | 重啟腳本 |

---

## 3. 敏感資訊掃描

公開前對 GitHub 最新版做一次全面掃描。

```bash
# clone GitHub 版本來檢查 (不要檢查本地 repo)
cd /tmp
git clone git@github.com-beakplatform:beakplatform/BeakPlatform.git beakplatform-audit
cd beakplatform-audit

# 搜尋密碼/token/key
grep -rn -i 'password\|passwd\|secret\|token\|api_key\|apikey' --include='*.py' --include='*.sh' --include='*.yml' --include='*.yaml' --include='*.env*' --include='*.md' .

# 搜尋內部 IP
grep -rn '192\.168\.\|10\.34\.' .

# 搜尋硬編碼密碼
grep -rn 'admin123\|postgres123\|P@ssw0rd' .

# 清理
cd /tmp && rm -rf beakplatform-audit
```

**所有搜尋結果必須人工逐條確認**，確保無實際敏感資訊外洩。

---

## 4. docs/ 放行審查

`docs/` 目前整目錄排除。公開前逐一審查，決定哪些文件可以放行：

- [ ] `docs/BeakPlatform_Installation_Guide.md` -- 安裝指南 (已移除硬編碼密碼)
- [ ] `docs/RATE_LIMITING.md` -- Rate Limiting 說明
- [ ] `docs/DEVTOOLS_AND_POC.md` -- 開發工具說明
- [ ] 其他文件依內容逐一判斷

放行的文件從 `push_github.sh` 排除清單中移除。

---

## 5. README 與授權

- [ ] 建立公開用 `README.md`（專案介紹、安裝方式、環境變數說明）
- [ ] 選擇並加入 `LICENSE` 檔案
- [ ] 確認 `.env.example` 內容適合公開

---

## 6. 最終確認

- [ ] 以上所有項目已完成
- [ ] GitHub repository Settings 確認為 private
- [ ] 團隊成員（如有）已知悉即將公開
- [ ] 切換為 public

---

*建立日期: 2026-03-22*
