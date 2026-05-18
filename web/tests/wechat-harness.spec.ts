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
        compiled_objects: {
          "concept:1A432000": {
            object_id: "1A432000",
            object_type: "concept",
            current_truth: "1A432000 上出现 E02 错因观察",
            evidence_level: "L1_repeated",
            supporting_event_ids: ["evt1", "evt2"],
            timeline_refs: [{ event_id: "evt1", observed_at: "2026-05-18T00:00:00Z" }],
          },
        },
        typed_graph_edges: [
          {
            edge_type: "question_tests_concept",
            from: { id: "wechat-harness-case-001", type: "question" },
            to: { id: "1A432000", type: "concept" },
            evidence_event_id: "evt1",
          },
          {
            edge_type: "error_points_to_training",
            from: { id: "E02", type: "error" },
            to: { id: "1A432000:training", type: "training" },
            evidence_event_id: "evt2",
          },
        ],
        typed_graph_readiness_gaps: [],
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
  await expect(page.getByTestId("learning-brain-visible-chain")).toContainText("Compiled truth + timeline");
  await expect(page.getByTestId("learning-brain-visible-chain")).toContainText("Typed graph chain");
  await expect(page.getByTestId("learning-brain-visible-chain")).toContainText("concept:1A432000");
  await expect(page.getByTestId("learning-brain-visible-chain")).toContainText("question_tests_concept");
});
