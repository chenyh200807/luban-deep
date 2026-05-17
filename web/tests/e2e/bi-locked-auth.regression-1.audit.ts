import { expect, test } from "@playwright/test";

test("locked BI shell does not call BI APIs without read or admin credentials", async ({ page }) => {
  // Regression: ISSUE-001 — locked BI shell fired protected API requests and flooded console with 401s.
  // Found by /qa on 2026-05-17.
  // Report: web/.gstack/qa-reports/qa-report-localhost-3782-2026-05-17.md
  const biApiRequests: string[] = [];
  const consoleErrors: string[] = [];

  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });

  await page.route("**/api/v1/bi/**", async (route) => {
    biApiRequests.push(route.request().url());
    await route.fulfill({
      status: 500,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ detail: "BI API should not be called while locked" }),
    });
  });

  await page.goto("/bi");

  await expect(page.getByText("401 BI 数据 API 尚未授权")).toBeVisible();
  await expect(page.getByRole("textbox", { name: "管理员用户名" })).toBeVisible();
  expect(biApiRequests).toEqual([]);
  expect(consoleErrors).toEqual([]);
});
