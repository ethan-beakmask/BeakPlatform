// PF-79 E2E 測試固定從 nginx 的 /beakplatform 前綴進入應用程式。
const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: __dirname,
  timeout: 30 * 1000,
  expect: {
    timeout: 10 * 1000,
  },
  retries: 0,
  workers: 1,
  reporter: 'list',
  outputDir: '../../test-results',
  use: {
    baseURL: 'http://192.168.0.16:7000/beakplatform',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
