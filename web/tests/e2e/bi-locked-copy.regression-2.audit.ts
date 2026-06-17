import { expect, test } from "@playwright/test";

test("locked BI access gate copy matches missing credential state", async ({ page }) => {
  // Regression: ISSUE-003 — locked member admin card claimed BI API Token was configured when it was not.
  // Found by /qa on 2026-05-17.
  // Report: web/.gstack/qa-reports/qa-report-localhost-3782-2026-05-17.md
  await page.goto("/bi?tab=member-ops");

  await expect(page.getByText("401 BI 数据 API 尚未授权")).toBeVisible();
  await expect(page.getByText("BI 数据 API 尚未授权；请输入管理员用户名和密码解锁会员管理能力。")).toBeVisible();
  await expect(page.getByText("BI API Token 已由系统配置，无需手动填写")).toHaveCount(0);
});
