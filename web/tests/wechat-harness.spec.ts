import { expect, test } from "@playwright/test";

test("wechat harness replays mini-program render contracts and supports MCQ interaction", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("/wechat-harness");
  await expect(page.getByTestId("wechat-harness-root")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Structured Table Formula Mcq Combo/i })).toBeVisible();
  await expect(page.getByTestId("phone-screen")).toBeVisible();
  await expect(page.getByTestId("harness-parity-status")).toContainText("一致");

  await page.getByTestId("mcq-option").filter({ hasText: "B" }).first().click();
  await page.getByTestId("mcq-submit").click();
  await expect(page.getByTestId("mcq-status")).toContainText("B");

  await page.getByTestId("harness-mode-stream").click();
  await expect(page.locator("[data-phase='streaming']").first()).toBeVisible();
  await page.getByRole("button", { name: "Final payload" }).click();
  await expect(page.locator("[data-phase='complete']").first()).toBeVisible();

  await page.getByTestId("harness-mode-history").click();
  await expect(page.getByTestId("harness-parity-status")).toContainText("一致");
  expect(consoleErrors).toEqual([]);
});

test("wechat harness mobile viewport keeps the phone surface readable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/wechat-harness");
  await expect(page.getByTestId("wechat-harness-root")).toBeVisible();
  await expect(page.getByTestId("phone-shell")).toBeVisible();
  await expect(page.getByTestId("phone-screen")).toBeVisible();

  const rootBox = await page.getByTestId("wechat-harness-root").boundingBox();
  expect(rootBox?.width).toBeLessThanOrEqual(390);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

