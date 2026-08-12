# PF-79 Playwright E2E 測試

這組測試把「資安案件處置中心」PF-79 的瀏覽器驗收固化成可重複執行的 Playwright 測試。

## 前提

- 服務已透過 nginx 暴露在 `http://192.168.0.16:7000/beakplatform`。
- 測試只走 `/beakplatform/dev/quick-login`，不使用帳密登入。
- quick-login 頁面需有企業 `beluga` 與帳號 `admin-ethanyu@beluga.com`。
- repo 根目錄已安裝 Playwright 1.62.1 與 chromium browser。

## 執行方式

```bash
bash scripts/run_e2e.sh
```

顯示瀏覽器：

```bash
bash scripts/run_e2e.sh --headed
```

查看參數：

```bash
bash scripts/run_e2e.sh --help
```

其餘參數會原樣傳給 `npx playwright test`，例如：

```bash
bash scripts/run_e2e.sh tests/e2e/od-pf79.spec.js -g PF-79
```

## 資料前提不足時

案件相關測試會從清單 API 動態挑資料，不硬編碼案件編號或 secure code。

- 找不到「不可簽核且仍在等待節點」的案件時，測試會 `skip` 並印出中文說明。
- 找不到「目前登入者可簽核」的案件時，測試會 `skip` 並提示需先製造待簽案件。

這些情況代表測試資料前提不足，不視為功能失敗。
