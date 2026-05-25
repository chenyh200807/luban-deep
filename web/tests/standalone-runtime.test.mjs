import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  buildStandaloneServerEnv,
  stageStandaloneRuntime,
} from "../scripts/standalone_runtime.mjs";

function makeTempRoot() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "deeptutor-standalone-test-"));
}

test("stageStandaloneRuntime copies static assets and public files into standalone runtime", () => {
  const root = makeTempRoot();
  const nextRoot = path.join(root, ".next");
  const standaloneRoot = path.join(nextRoot, "standalone");
  const standaloneNextRoot = path.join(standaloneRoot, ".next");
  const staticSource = path.join(nextRoot, "static");
  const publicSource = path.join(root, "public");

  fs.mkdirSync(path.join(staticSource, "chunks"), { recursive: true });
  fs.mkdirSync(path.join(publicSource, "images"), { recursive: true });
  fs.mkdirSync(standaloneNextRoot, { recursive: true });

  fs.writeFileSync(path.join(staticSource, "chunks", "main.js"), "console.log('ok')");
  fs.writeFileSync(path.join(publicSource, "images", "logo.svg"), "<svg />");

  const result = stageStandaloneRuntime({ rootDir: root });

  assert.equal(result.standaloneServerExists, false);
  assert.equal(
    fs.readFileSync(
      path.join(standaloneNextRoot, "static", "chunks", "main.js"),
      "utf8",
    ),
    "console.log('ok')",
  );
  assert.equal(
    fs.readFileSync(
      path.join(standaloneRoot, "public", "images", "logo.svg"),
      "utf8",
    ),
    "<svg />",
  );
});

test("buildStandaloneServerEnv preserves port and hostname flags for standalone server", () => {
  const env = buildStandaloneServerEnv(
    {
      PORT: "3000",
      HOSTNAME: "0.0.0.0",
    },
    ["--hostname", "127.0.0.1", "-p", "3012"],
  );

  assert.equal(env.HOSTNAME, "127.0.0.1");
  assert.equal(env.PORT, "3012");
});
