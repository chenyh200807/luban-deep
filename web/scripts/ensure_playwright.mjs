import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";

const isWindows = process.platform === "win32";
const playwrightBin = isWindows
  ? "node_modules/.bin/playwright.cmd"
  : "node_modules/.bin/playwright";

function run(command, args) {
  const result = spawnSync(command, args, {
    stdio: "inherit",
    shell: isWindows,
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

if (!existsSync(playwrightBin)) {
  run("npm", ["ci"]);
}

run("npx", ["playwright", "install", "chromium"]);
