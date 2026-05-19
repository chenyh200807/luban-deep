# ESLint 9.39.2 Plugin Incompatibility — Diagnosis (FOLLOWUP-eslint)

| 字段 | 值 |
| --- | --- |
| 日期 | 2026-05-19 |
| 类型 | Diagnosis only (no fix in this branch) |
| 状态 | Diagnosed — fix deferred to dedicated follow-up PR |
| 触发 | `/qa-only` 2026-05-19 verification phase, `cd web && npx eslint app/wechat-harness/WechatHarnessClient.tsx` 报错 |
| 影响 | `npm run lint` 完全 broken；**不阻塞** `npm run build`、`npm run test:wechat-harness`、`tsc`、Playwright |

---

## 1. 现状 / 报错

```
TypeError: Cannot read properties of undefined (reading 'preprocessConfig')
    at Object.<anonymous> (web/node_modules/eslint/lib/config/flat-config-array.js:182:21)
ESLint: 9.39.2
```

切到 Node 22 LTS 后错误变为上面这个（Node 24 时是 `ConfigCommentParser is not a constructor`）；说明问题不在 Node 版本，而在 **eslint 9 flat config 与某个 plugin 的初始化层冲突**。

---

## 2. Config + 依赖谱系（调研事实）

| 项 | 值 |
| --- | --- |
| Config 文件 | `web/eslint.config.mjs`（**flat config**，eslint 9 推荐） |
| Imports | `eslint-config-next@16.2.6`（spread 进 array）+ 自写 `./eslint/i18n-plugin.mjs` |
| `eslint-config-next` 传递依赖 | `eslint-plugin-react@7.37.5`、`eslint-plugin-react-hooks@7.0.1`、`eslint-plugin-import@2.32.0`、`eslint-plugin-jsx-a11y@6.10.2`、`@next/eslint-plugin-next@16.2.6`、`typescript-eslint@8.52.0` |
| `eslint` 版本 | `9.39.2` |

每个 plugin 在 `package.json.peerDependencies.eslint` 中声明的兼容范围都**包含 `^9`**（即理论上都兼容 eslint 9）；版本号上看不出明显 mismatch。

---

## 3. Root Cause（调研 verdict）

不是简单的版本不兼容，而是 **`eslint-plugin-react@7.37.5` 在 eslint 9 环境下 `require()` 阶段卡死**：

- subagent 实测：单独 `node -e 'require("eslint-plugin-react")'` 在 Node 22 + eslint 9 工程内 → **timeout**
- `flat-config-array.js:182` 的 `[ConfigArraySymbol.preprocessConfig](config)` 期望 plugin module 的某个 internal 对象存在 → undefined 触发 `preprocessConfig` 报错
- infinite recursion / circular dependency 信号

也就是说，**peerDependencies 声明的兼容范围与实际运行兼容性脱节**——plugin 自称支持 eslint 9，但在 flat config 初始化路径上失败。

---

## 4. 修复路径（first-principles 三条）

| Option | 内容 | Diff 大小 | 风险 |
| --- | --- | --- | --- |
| **A** 降 eslint 到 8.57.0 | `package.json: eslint": "^8.57.0"` + `npm i` | ~1 行 + lock file | eslint 8 已 EOL，长期安全更新缺失 |
| **B** 升 `eslint-plugin-react` 到 ^7.38+ 或 ^8 | 同上 + 可能升 `eslint-config-next` | 1-2 行 + lock | 升级可能引入大量新 lint warning / rule breaking |
| **C** 拆解 `eslint.config.mjs`，移除 `...nextConfig`，手写最小规则 | 重写 config file | ~30 行 | 失去 next.js 官方推荐规则，长期维护成本上升 |

### Less-is-more 推荐

**Option C → Option B**：先做 §6 的"侦察"动作精确定位 culprit plugin，再升 culprit 的最小版本，**不做大范围升级**。

但本次本 PR 不做。理由：

1. **不在关键路径**：`npm run lint` broken **不阻塞** build / test / 发布
2. **复杂度**：需要先单独跑实验确定 culprit，再尝试升级，**单独 PR 范围合理**
3. **打补丁风险**：在 surgical hardening PR 里强塞 eslint 修复 = scope creep（违背 surgical changes 纪律）

---

## 5. 临时 workaround（当下能用的代码质量手段）

| 手段 | 命令 | 覆盖 |
| --- | --- | --- |
| TypeScript 类型检查 | `cd web && npx tsc --noEmit -p .` | 类型错误、unused imports（部分） |
| Next.js build | `cd web && npm run build` | 自带 lint subset（react-hooks 等） |
| Playwright | `npm run test:wechat-harness` | 行为级别保证 |
| pytest | `pytest -q` | Python 后端 |

→ 当下代码质量门并未失守，只是少了一个 dedicated lint 工具。

---

## 6. 收口路径（独立 follow-up PR 模板）

未来某次专门处理 eslint 时，按下面步骤：

1. **侦察 culprit**（30 分钟）
   ```bash
   cd web
   # 备份 config
   cp eslint.config.mjs eslint.config.mjs.bak
   # 极简化：先只保留 ignores
   cat > eslint.config.mjs <<'EOF'
   export default [{ ignores: ["**/node_modules/**", "**/.next/**"] }];
   EOF
   npx eslint . --max-warnings 0  # 如果通过：是 plugin 问题
   # 然后逐个 plugin 加回，每加一个跑一次
   ```
2. **针对 culprit plugin 升级或替换**
   - 看 culprit 的 GitHub release notes 找 eslint 9 兼容 release
   - 如果没有：评估替代品（如 `@biomejs/biome`、`oxlint`）
3. **跑全仓库 lint，处理新出现的 warning/error**
4. **commit**: `chore(web): unblock npm run lint via <plugin>@<version>`

---

## 7. 不确定性

| # | 项 | 应对 |
| --- | --- | --- |
| U1 | subagent 仅推断 `eslint-plugin-react` 是 culprit，未真正 git bisect 验证 | §6 第 1 步实际做 plugin 隔离实验时会真正定位 |
| U2 | `eslint-config-next@16.2.6` 在 Next.js 16.2 时是新发布，可能官方未充分测试 flat config 路径 | 查 Next.js GitHub issues 看是否有同类 bug report，作为升 Next.js 与否的决策依据 |
| U3 | 升级 plugin 后是否会引入大量新 lint warning | 升级后第一次 `npm run lint` 应该用 `--max-warnings 9999`，统计新 warning 数量再决定是否回滚或修复 |

---

## 8. 当前 PR 的决策

本 PR (chore/wechat-harness-followups) **不修 eslint**。本 doc 作为 commit 3：诊断结果 + 修复路线图。

未来 PR 接手时，直接 follow §6。本次没有发明任何中间状态、临时 patch、抽象层——thin wrappers fat skills + less is more。
