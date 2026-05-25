import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const ROOT = process.cwd();
const STANDALONE_SERVER = path.join(ROOT, ".next", "standalone", "server.js");

async function waitForUrl(url, timeoutMs) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const response = await fetch(url);
      return response;
    } catch (_error) {
      await new Promise(resolve => setTimeout(resolve, 200));
    }
  }
  throw new Error(`timed out waiting for ${url}`);
}

test("production runtime flag exposes wechat harness instead of prerendered 404", async () => {
  if (!fs.existsSync(STANDALONE_SERVER)) {
    test.skip("standalone server not built");
    return;
  }

  const port = 3123;
  const server = spawn(process.execPath, [STANDALONE_SERVER], {
    cwd: ROOT,
    env: {
      ...process.env,
      PORT: String(port),
      HOSTNAME: "127.0.0.1",
      NODE_ENV: "production",
      DEEPTUTOR_ENABLE_WECHAT_HARNESS: "true",
    },
    stdio: "ignore",
  });

  try {
    const response = await waitForUrl(`http://127.0.0.1:${port}/wechat-harness`, 10000);
    assert.equal(response.status, 200);

    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
      const consoleErrors = [];
      page.on("console", message => {
        if (message.type() === "error") consoleErrors.push(message.text());
      });

      await page.goto(`http://127.0.0.1:${port}/wechat-harness`, {
        waitUntil: "domcontentloaded",
      });
      await page.waitForTimeout(2500);

      assert.equal(
        await page.locator('[data-testid="wechat-harness-root"]').isVisible(),
        true,
        "runtime-enabled harness should render the main harness root",
      );
      assert.equal(
        await page.getByRole("heading", { name: /Structured Table Formula Mcq Combo/i }).isVisible(),
        true,
        "runtime-enabled harness should render canonical fixture content",
      );
      assert.deepEqual(consoleErrors, []);
    } finally {
      await browser.close();
    }
  } finally {
    server.kill("SIGTERM");
    await new Promise(resolve => server.once("exit", resolve));
  }
});
