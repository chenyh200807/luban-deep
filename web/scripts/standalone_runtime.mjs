#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

function copyTreeIfExists(source, destination) {
  if (!fs.existsSync(source)) return false;
  fs.rmSync(destination, { recursive: true, force: true });
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.cpSync(source, destination, { recursive: true });
  return true;
}

export function stageStandaloneRuntime(options = {}) {
  const rootDir = options.rootDir || process.cwd();
  const nextRoot = path.join(rootDir, ".next");
  const standaloneRoot = path.join(nextRoot, "standalone");
  const standaloneNextRoot = path.join(standaloneRoot, ".next");
  const standaloneServer = path.join(standaloneRoot, "server.js");

  const standaloneServerExists = fs.existsSync(standaloneServer);
  const stagedStatic = copyTreeIfExists(
    path.join(nextRoot, "static"),
    path.join(standaloneNextRoot, "static"),
  );
  const stagedPublic = copyTreeIfExists(
    path.join(rootDir, "public"),
    path.join(standaloneRoot, "public"),
  );

  return {
    rootDir,
    standaloneRoot,
    standaloneServer,
    standaloneServerExists,
    stagedStatic,
    stagedPublic,
  };
}

export function buildStandaloneServerEnv(baseEnv, args = []) {
  const env = { ...baseEnv };
  for (let index = 0; index < args.length; index += 1) {
    const value = args[index];
    if ((value === "-p" || value === "--port") && args[index + 1]) {
      env.PORT = args[index + 1];
      index += 1;
      continue;
    }
    if (value === "--hostname" && args[index + 1]) {
      env.HOSTNAME = args[index + 1];
      index += 1;
    }
  }
  return env;
}

async function startRuntime() {
  const staged = stageStandaloneRuntime();
  const forwardedArgs = process.argv.slice(2);
  const command = staged.standaloneServerExists
    ? process.execPath
    : path.join(process.cwd(), "node_modules", "next", "dist", "bin", "next");
  const args = staged.standaloneServerExists
    ? [staged.standaloneServer]
    : ["start", ...forwardedArgs];
  const env = staged.standaloneServerExists
    ? buildStandaloneServerEnv(process.env, forwardedArgs)
    : process.env;

  if (staged.standaloneServerExists) {
    console.log(
      `[standalone-runtime] using ${path.relative(process.cwd(), staged.standaloneServer)}`
    );
  } else {
    console.warn(
      "[standalone-runtime] standalone server missing; falling back to next start"
    );
  }

  await new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: process.cwd(),
      env,
      stdio: "inherit",
    });
    child.on("exit", code => {
      if (typeof code === "number") {
        process.exitCode = code;
        resolve();
        return;
      }
      reject(new Error("standalone runtime exited without status code"));
    });
    child.on("error", reject);
  });
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const command = process.argv[2] || "--stage";

  if (command === "--stage") {
    const staged = stageStandaloneRuntime();
    console.log(JSON.stringify(staged, null, 2));
  } else if (command === "--start") {
    process.argv.splice(2, 1);
    await startRuntime();
  } else {
    console.error(`Unknown command: ${command}`);
    process.exit(1);
  }
}
