import { expect, test, type Page } from "@playwright/test";

async function mockBiApis(page: Page) {
  await page.route("**/api/v1/bi/**", async (route) => {
    await route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ data: {} }),
    });
  });
}

test.describe("BI Command Deck audit", () => {
  test("public bi surface loads without generic workspace fallback", async ({ page }) => {
    await mockBiApis(page);

    await page.goto("/bi");

    await expect(page.getByText("BI workspace unavailable")).toHaveCount(0);
  });

  test("bi deck exposes the new heading", async ({ page }) => {
    await mockBiApis(page);

    await page.goto("/bi");

    await expect(page.getByRole("heading", { name: "DeepTutor BI Deck" })).toBeVisible();
    await expect(page.getByText("经营、质量、会员、TutorBot 四条主线的一体化指挥舱")).toBeVisible();
  });

  test("bi deck exposes the new primary tabs", async ({ page }) => {
    await mockBiApis(page);

    await page.goto("/bi");

    await expect(page.getByRole("link", { name: "Overview" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Quality" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Member Ops" })).toBeVisible();
    await expect(page.getByRole("link", { name: "TutorBot" })).toBeVisible();
  });

  test("bi deck removes old in-page anchor navigation", async ({ page }) => {
    await mockBiApis(page);

    await page.goto("/bi");

    await expect(page.locator('a[href="#trend"]')).toHaveCount(0);
    await expect(page.locator('a[href="#knowledge"]')).toHaveCount(0);
    await expect(page.locator('a[href="#capability"]')).toHaveCount(0);
  });
});
