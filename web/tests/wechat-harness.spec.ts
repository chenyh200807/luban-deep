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

test("wechat harness displays learning brain grading and synthesis result", async ({ page }) => {
  await page.route("**/api/v1/learning-brain/harness-case-grading", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        ok: true,
        user_id: "wechat_harness_learning_brain",
        grading_results: [
          {
            question_id: "wechat-harness-case-001",
            score_label: "0/1",
            missed_points: ["应组织专家论证"],
            rewrite: "应组织专家论证，并编制专项施工方案后按规定审批。",
            next_training_signal: {
              concept: "1A432000",
              focus: "危险性较大工程专项方案程序",
              mode: "projected_rubric",
            },
          },
        ],
        event_count: 2,
        created_claim_count: 1,
        output_projection_hash: "sha256:test",
        projection_subject: "construction_exam_learning_truth",
        weak_points: [
          {
            concept_id: "1A432000",
            error_code: "E02",
            evidence_level: "L1_repeated",
            supporting_event_ids: ["evt1", "evt2"],
          },
        ],
        visible_sections: {
          current_truth: [
            {
              event_id: "",
              display_label: "知识点",
              display_title: "知识点：危险性较大工程专项方案程序",
              display_meta: "1A432000",
              evidence_level_label: "重复观察",
            },
          ],
          evidence_flow: [
            {
              event_id: "evt1",
              display_label: "案例题",
              display_title: "案例题：专项训练 001",
              display_meta: "案例题：专项训练 001",
              display_path: "案例题：专项训练 001 → 知识点：1A432000",
            },
          ],
          next_training: [
            {
              event_id: "",
              display_label: "训练建议",
              display_title: "训练建议：危险性较大工程专项方案程序",
              display_meta: "知识点：危险性较大工程专项方案程序；错因：采分点遗漏",
              evidence_level_label: "重复观察",
            },
          ],
        },
        typed_graph_edge_count: 7,
      },
    });
  });

  await page.goto("/wechat-harness");
  await expect(page.getByTestId("learning-brain-qa")).toBeVisible();
  await page.getByTestId("learning-brain-run").click();
  await expect(page.getByTestId("learning-brain-result")).toContainText("0/1");
  await expect(page.getByTestId("learning-brain-result")).toContainText("应组织专家论证");
  await expect(page.getByTestId("learning-brain-result")).toContainText("construction_exam_learning_truth");
  // visible-chain must follow learning_brain_read_model.visible_sections contract
  // (current_truth / evidence_flow / next_training, in Chinese; not internal projection labels)
  const visibleChain = page.getByTestId("learning-brain-visible-chain");
  await expect(visibleChain).toContainText("当前可信结论");
  await expect(visibleChain).toContainText("证据流");
  await expect(visibleChain).toContainText("下一步训练");
  await expect(visibleChain).toContainText("知识点：危险性较大工程专项方案程序");
  await expect(visibleChain).toContainText("训练建议：危险性较大工程专项方案程序");
  // Regression guard: contract violations must not return
  await expect(visibleChain).not.toContainText("Compiled truth + timeline");
  await expect(visibleChain).not.toContainText("Typed graph chain");
});
