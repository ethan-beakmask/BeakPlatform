const { test, expect } = require('@playwright/test');
const { quickLogin } = require('./helpers/login');

const CASES_PATH = '/beakplatform/open-defense/security-cases';
const CASES_API = '/beakplatform/api/open_defense/cases?status=open';
const PENDING_TASKS_API_PART = '/api/form-center/pending-tasks/';

async function fetchOpenCases(page) {
  const response = await page.request.get(CASES_API);
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  return Array.isArray(body.data) ? body.data : [];
}

async function gotoSecurityCases(page) {
  await page.goto(CASES_PATH);
  await expect(page.locator('.od-header')).toBeVisible();
}

async function disableMineOnlyFilterIfActive(page) {
  const mineOnlyButton = page.locator('.od-header button', { hasText: '僅我可簽核' });
  await expect(mineOnlyButton).toBeVisible();
  const buttonClass = await mineOnlyButton.getAttribute('class');

  if (buttonClass && buttonClass.includes('btn-primary')) {
    const casesReloaded = page.waitForResponse((response) => (
      response.url().includes(CASES_API) && response.request().method() === 'GET'
    ));
    await Promise.all([
      casesReloaded,
      mineOnlyButton.click(),
    ]);
  }
}

async function clickCaseByExecutionCode(page, executionCode) {
  const caseItem = page
    .locator('.sc-case-item')
    .filter({ has: page.locator('.od-mono', { hasText: executionCode }) });
  await expect(caseItem.first()).toBeVisible();
  await caseItem.first().click();
}

test.describe.serial('PF-79 資安案件處置中心', () => {
  test.beforeEach(async ({ page }) => {
    await quickLogin(page);
  });

  test('A. 點不可簽核案件不再打出 403', async ({ page }) => {
    // 驗證資料前提：需要至少一筆還在等待節點、但目前登入者不可簽核的案件。
    await gotoSecurityCases(page);
    await disableMineOnlyFilterIfActive(page);

    const cases = await fetchOpenCases(page);
    const target = cases.find((item) => item.waiting_node && item.can_act === false);
    if (!target) {
      console.log('略過：找不到不可簽核且仍在等待節點的案件，需先製造他人待簽案件。');
      test.skip(true, '找不到不可簽核且仍在等待節點的案件，需先製造他人待簽案件。');
    }

    const pendingTaskRequests = [];
    const consoleErrors = [];
    page.on('request', (request) => {
      if (request.url().includes(PENDING_TASKS_API_PART)) {
        pendingTaskRequests.push(request.url());
      }
    });
    page.on('console', (message) => {
      if (message.type() === 'error') {
        consoleErrors.push(message.text());
      }
    });

    await clickCaseByExecutionCode(page, target.execution_code);

    await expect(page.locator('#sc-detail')).toContainText(target.execution_code);
    await expect(
      page.locator('#sc-detail p.sc-field-label')
        .filter({ hasText: target.waiting_node.node_name })
        .filter({ hasText: '您不是此節點的指定簽核人' }),
    ).toBeVisible();
    await expect(page.locator('#sc-detail .sc-actions button')).toHaveCount(0);

    expect(pendingTaskRequests, '不可簽核案件不應請求 pending-tasks API').toHaveLength(0);
    expect(consoleErrors, '不可簽核案件點擊後不應產生 console error').toHaveLength(0);
  });

  test('B. 可簽核案件的詳情與處置按鈕仍正常', async ({ page }) => {
    // 驗證資料前提：需要至少一筆目前登入者可簽核的進行中案件。
    await gotoSecurityCases(page);

    const cases = await fetchOpenCases(page);
    const target = cases.find((item) => item.can_act === true);
    if (!target) {
      console.log('略過：找不到可簽核案件；可簽核案件可能已被簽完，需先製造待簽案件。');
      test.skip(true, '可簽核案件可能已被簽完，需先製造待簽案件。');
    }

    const pendingTaskResponse = page.waitForResponse((response) => (
      response.url().includes(PENDING_TASKS_API_PART)
      && response.request().method() === 'GET'
      && response.status() === 200
    ));

    await Promise.all([
      pendingTaskResponse,
      clickCaseByExecutionCode(page, target.execution_code),
    ]);

    await expect(page.locator('#sc-detail')).toContainText(target.execution_code);
    await expect(page.locator('#sc-detail .sc-actions button').first()).toBeVisible();
    await expect(page.locator('#sc-detail .sc-actions button')).not.toHaveCount(0);
    await expect(page.locator('#sc-detail', { hasText: '您不是此節點的指定簽核人' })).toHaveCount(0);

    // 絕對不要點擊任何處置按鈕；這些按鈕會真的完成簽核並改變案件狀態，讓測試無法重複執行。
  });

  test('C. 四頁副標已移除', async ({ page }) => {
    // 驗證 OpenDefense 四個管理頁的頁首不再渲染副標 p 元素。
    for (const pageName of ['decisions', 'event-routing', 'intake-keys', 'service-accounts']) {
      await page.goto(`/beakplatform/open-defense/${pageName}`);
      await expect(page.locator('.od-header')).toBeVisible();
      await expect(page.locator('.od-header p')).toHaveCount(0);
    }
  });

  test('D. intake-keys 的 API Key 管理入口保留 nginx 前綴', async ({ page }) => {
    // 驗證實際可點擊的管理入口 href 與導向 URL 都包含 /beakplatform 前綴。
    await page.goto('/beakplatform/open-defense/intake-keys');
    const apiKeyLink = page.locator('.od-header a', { hasText: 'API Key 管理' });

    await expect(apiKeyLink).toBeVisible();
    await expect(apiKeyLink).toHaveAttribute('href', '/beakplatform/security/api-keys/');
    await Promise.all([
      page.waitForURL('http://192.168.0.16:7000/beakplatform/security/api-keys/'),
      apiKeyLink.click(),
    ]);
  });
});
