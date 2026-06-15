import { spawn } from 'node:child_process'
import { access, cp, lstat, mkdir, readlink, rm, symlink } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const webRoot = path.resolve(scriptDir, '..')
const standaloneRoot = path.join(webRoot, '.next', 'standalone')
const standaloneNextRoot = path.join(standaloneRoot, '.next')
const standaloneServer = path.join(standaloneRoot, 'server.js')

async function pathExists(targetPath) {
  try {
    await access(targetPath)
    return true
  } catch {
    return false
  }
}

async function ensureSymlinkOrCopy(sourcePath, targetPath) {
  const relativeSource = path.relative(path.dirname(targetPath), sourcePath)

  if (await pathExists(targetPath)) {
    const stats = await lstat(targetPath)
    if (stats.isSymbolicLink()) {
      const linkedPath = await readlink(targetPath)
      if (linkedPath === relativeSource) return
    }
    await rm(targetPath, { force: true, recursive: true })
  }

  await mkdir(path.dirname(targetPath), { recursive: true })
  try {
    await symlink(relativeSource, targetPath, 'junction')
  } catch {
    await cp(sourcePath, targetPath, { force: true, recursive: true })
  }
}

async function prepareStandaloneArtifacts() {
  if (!(await pathExists(standaloneServer))) {
    throw new Error(
      'missing standalone server: run `npm run build` before `npm run start:standalone:smoke`'
    )
  }

  const staticSource = path.join(webRoot, '.next', 'static')
  if (!(await pathExists(staticSource))) {
    throw new Error('missing .next/static: run `npm run build` before standalone smoke')
  }

  const publicSource = path.join(webRoot, 'public')
  await ensureSymlinkOrCopy(staticSource, path.join(standaloneNextRoot, 'static'))
  if (await pathExists(publicSource)) {
    await ensureSymlinkOrCopy(publicSource, path.join(standaloneRoot, 'public'))
  }
}

async function main() {
  await prepareStandaloneArtifacts()

  const child = spawn(process.execPath, ['server.js'], {
    cwd: standaloneRoot,
    env: process.env,
    stdio: 'inherit',
  })

  const forwardSignal = signal => {
    if (!child.killed) child.kill(signal)
  }

  process.on('SIGINT', forwardSignal)
  process.on('SIGTERM', forwardSignal)

  child.on('exit', (code, signal) => {
    process.off('SIGINT', forwardSignal)
    process.off('SIGTERM', forwardSignal)
    if (signal) {
      process.kill(process.pid, signal)
      return
    }
    process.exit(code ?? 0)
  })
}

main().catch(error => {
  console.error(error instanceof Error ? error.message : String(error))
  process.exit(1)
})
