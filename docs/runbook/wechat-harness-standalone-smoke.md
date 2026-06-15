# Wechat Harness Standalone Smoke

本 runbook 只服务 `web/` 本地 smoke，不替代真实微信 DevTools 验收。

## 结论

不要再用 `next start` 充当本地 production-style smoke server。

当前 `web` 使用 `output: 'standalone'`。直接跑 `next start` 或只跑
`node .next/standalone/server.js`，都会遗漏 standalone 目录需要的
`.next/static` / `public` 资源挂载，结果是：

- SSR HTML 200
- `_next/static/*` / 字体资源 404
- 页面不 hydrate
- 所有 click / filter / MCQ / error panel 看起来都像“组件坏了”

这是假红，不是 `WechatHarnessClient` 真实回归。

## Canonical Commands

在 `web/` 目录下：

```bash
npm run build
npm run test:wechat-harness:e2e:self-hosted
```

如果只想单独起 server：

```bash
npm run build
PORT=3112 DEEPTUTOR_ENABLE_WECHAT_HARNESS=true npm run start:standalone:smoke
```

`start:standalone:smoke` 会先准备两类资源，再启动 `web/.next/standalone/server.js`：

- `.next/static -> .next/standalone/.next/static`
- `public -> .next/standalone/public`

优先建立符号链接；不支持时退化为复制。

## Expected Signals

正确的 standalone smoke 应满足：

- `/_next/static/*` 不再 404
- 页面可 hydrate，Playwright click/filter 生效
- `web/tests/wechat-harness.spec.ts` 在 self-hosted standalone 模式通过
- 移动端 `wechat-harness-root` 与 `/intro` 的滚动契约在 production-style smoke 下保持通过

## Boundary

- `/wechat-harness` 仍然只是 `wechat_harness_shadow`
- 它不能替代 `yousenwebview -> packageDeeptutor` 的 `real_wechat_package`
- 真微信入口仍按 DevTools CLI / 真机证据单独验收
