const { expect } = require('@playwright/test');

const QUICK_LOGIN_PATH = '/beakplatform/dev/quick-login';
const DASHBOARD_PATTERN = /\/beakplatform\/dashboard(?:[/?#].*)?$/;

async function quickLogin(page, {
  enterprise = 'beluga',
  email = 'admin-ethanyu@beluga.com',
} = {}) {
  await page.goto(QUICK_LOGIN_PATH);

  await expect(page.getByRole('heading', { name: '選擇企業' })).toBeVisible();
  await page.getByText(enterprise, { exact: true }).first().click();

  const account = page.getByText(email, { exact: true }).first();
  await expect(account).toBeVisible();
  await Promise.all([
    page.waitForURL(DASHBOARD_PATTERN),
    account.click(),
  ]);
}

module.exports = {
  quickLogin,
};
