# 阿里云 ECS 部署（8.135.42.145）

这份说明对应当前主服务器 `8.135.42.145`，部署目录固定为 `/root/deeptutor`。

## 发布硬护栏

- SSH 写入铁律：DeepTutor 在阿里云上只允许修改 `Aliyun-ECS-2:/root/deeptutor` 目录内的文件内容，其他路径一概不允许修改。
- 任何远端写操作，包括 `ssh` 内命令、`rsync`、`scp`、`docker cp`、热修、备份、回滚、部署脚本、临时验证产物，目标路径都必须落在 `/root/deeptutor` 内；不得用 `/tmp`、`/root`、`/root/luban` 或系统目录做绕行写入。
- `/root/luban`、`/etc`、`/usr`、`/var`、`/opt`、`/home`、nginx 系统配置、systemd、全局 cron、宿主机 Docker 配置等非 `/root/deeptutor` 路径全部视为只读观察面；只能读，不能创建、编辑、删除、移动、覆盖、改权限或安装依赖。
- 如果一次修复确实需要 `/root/deeptutor` 之外的宿主机改动，必须停止发布流程，先单独向用户说明目标路径、必要性、风险和替代方案；未获得新的明确授权前，一律不改。
- 默认只允许从干净候选分支发布；`main` 或 dirty tree 会被 [scripts/sync_to_aliyun.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/sync_to_aliyun.sh) 直接拒绝。
- 默认只允许发往 `Aliyun-ECS-2:/root/deeptutor`；如果要改主机或目录，必须显式设置 `ALLOW_NON_CANONICAL_DEPLOY=1`。
- [scripts/sync_to_aliyun.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/sync_to_aliyun.sh) 每次覆盖远端前都会先生成代码快照 `data/releases/code/<release_id>.tar.gz`。
- [scripts/deploy_aliyun.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/deploy_aliyun.sh) 和 [scripts/redeploy_aliyun_fast.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/redeploy_aliyun_fast.sh) 在远端重启前都会先执行 `python3 scripts/backup_data.py`，自动生成本次发布的 runtime rollback 基线。
- 发布完成的唯一公网验收口径是：本地发起端对 `https://test2.yousenjiaoyu.com` 的 `front page`、`/healthz`、`/readyz` 探针全部通过；`docker compose ps` 或远端 `127.0.0.1` 只能算内部就绪，不能直接当成“已上线”。
- Observability 默认不走公网暴露；阿里云生产环境统一通过 SSH/localhost 抓取 `/metrics` 与 `/metrics/prometheus`。
- 紧急绕过护栏必须显式设置：
  - `ALLOW_DIRTY_DEPLOY=1`
  - `ALLOW_MAIN_BRANCH_DEPLOY=1`
  - `ALLOW_NON_CANONICAL_DEPLOY=1`

建议发布前固定执行：

```bash
git branch --show-current
git status --short
python scripts/check_contract_guard.py
python scripts/verify_runtime_assets.py
```

## 当前服务器结论

- 当前可用服务器：`Aliyun-ECS-2` -> `8.135.42.145`
- 现网项目目录：`/root/luban`
- 不要把 `deeptutor` 上传到 `/root/luban`
- 当前可直接使用的 DeepTutor 端口：
  - 前端 `3782`
  - 后端 `8001`
- 宿主机 `80/443` 已由现有 nginx 占用，但当前发布与公网验收 authority 已统一收口到 `https://test2.yousenjiaoyu.com`；`3782/8001` 只保留给 SSH 登录后的内部排障与 localhost 探针

## 仓库内新增的部署入口

- 上传脚本：[scripts/sync_to_aliyun.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/sync_to_aliyun.sh)
- 快速重启脚本：[scripts/restart_aliyun.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/restart_aliyun.sh)
- 后端快速发布脚本：[scripts/redeploy_aliyun_fast.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/redeploy_aliyun_fast.sh)
- 一键部署脚本：[scripts/deploy_aliyun.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/deploy_aliyun.sh)
- 发布环境校验脚本：[scripts/validate_aliyun_release_env.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/validate_aliyun_release_env.sh)
- 观测内网验收脚本：[scripts/verify_aliyun_observability.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/verify_aliyun_observability.sh)
- 代码回滚脚本：[scripts/rollback_aliyun_release.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/rollback_aliyun_release.sh)
- 服务器启动脚本：[scripts/server_bootstrap_aliyun.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/server_bootstrap_aliyun.sh)
- 运行态备份与恢复 runbook：[docs/zh/guide/runtime-backup-restore.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/zh/guide/runtime-backup-restore.md)
- 备份定时任务样例：[deployment/backup/runtime-backup.cron.example](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deployment/backup/runtime-backup.cron.example)
- 运行态观测与告警说明：[docs/zh/guide/runtime-observability.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/zh/guide/runtime-observability.md)
- 环境变量模板：[deployment/aliyun/aliyun.env.example](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deployment/aliyun/aliyun.env.example)
- Langfuse 联通覆盖：[deployment/aliyun/docker-compose.langfuse.yml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deployment/aliyun/docker-compose.langfuse.yml)
- nginx 示例：
  - [deployment/aliyun/nginx/deeptutor-web.conf.example](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deployment/aliyun/nginx/deeptutor-web.conf.example)
  - [deployment/aliyun/nginx/deeptutor-api.conf.example](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deployment/aliyun/nginx/deeptutor-api.conf.example)

## 首次部署

### 1. 准备服务器 `.env`

第一次部署时，脚本会在服务器 `/root/deeptutor/.env` 不存在时，自动从模板复制一份并停止。

模板里已经预设：

- `BACKEND_PORT=8001`
- `FRONTEND_PORT=3782`
- `NEXT_PUBLIC_API_BASE_EXTERNAL=http://8.135.42.145:8001`
- 本地发布验收默认域名固定为：
  - `PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com`
- `SERVICE_ENV=production`
- `APP_ENV=production`
- `MEMBER_CONSOLE_USE_REAL_SMS=true`

你需要补齐至少这些项：

- `LLM_API_KEY`
- `EMBEDDING_API_KEY`
- `WECHAT_MP_APP_ID`
- `WECHAT_MP_APP_SECRET`
- `DEEPTUTOR_AUTH_SECRET`
- `DEEPTUTOR_ADMIN_USER_IDS`
- `ALIYUN_SMS_ACCESS_KEY_ID`
- `ALIYUN_SMS_ACCESS_KEY_SECRET`
- `ALIYUN_SMS_SIGN_NAME`
- `ALIYUN_SMS_TEMPLATE_CODE`

如果你继续使用 DashScope，这两个 key 可以相同。

如果不显式把 `SERVICE_ENV` / `APP_ENV` 设成 `production`，或者没把
`MEMBER_CONSOLE_USE_REAL_SMS` 打开，小程序验证码会退回调试模式，接口返回
`debug_code`，不会真正发短信。

认证上线额外约束：

- production access token 只接受显式 `DEEPTUTOR_AUTH_SECRET` 或兼容别名 `MEMBER_CONSOLE_AUTH_SECRET`
- 生产 `.env` 中禁止把 `DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE` / `DEEPTUTOR_EXTERNAL_AUTH_SESSIONS_FILE` 指到 `/root/luban`
- 发布脚本会在远端重启前自动执行 `validate_aliyun_release_env.sh`；缺少 `DEEPTUTOR_AUTH_SECRET` 或 `DEEPTUTOR_ADMIN_USER_IDS` 会直接拒绝发布

模板里还默认给了阿里云构建加速参数：

- `APT_MIRROR=https://mirrors.aliyun.com/debian`
- `SECURITY_MIRROR=https://mirrors.aliyun.com/debian-security`
- `RUSTUP_DIST_SERVER=https://rsproxy.cn`
- `RUSTUP_UPDATE_ROOT=https://rsproxy.cn/rustup`
- `PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/`

### 2. 上传代码

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
bash scripts/sync_to_aliyun.sh once
```

说明：

- 目标目录固定为 `/root/deeptutor`
- 默认目标主机固定为 `Aliyun-ECS-2`
- dirty tree 或 `main` 会被脚本直接拒绝
- 会排除 `.env`、`data/`、`.git`、`.venv`、`node_modules`
- 这样不会覆盖服务器上已经生成的数据和密钥

如果你想开发时持续同步：

```bash
bash scripts/sync_to_aliyun.sh watch
```

### 3. 启动部署

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/deploy_aliyun.sh
```

脚本会做这些事：

1. 同步仓库到 `Aliyun-ECS-2:/root/deeptutor`
2. 先在远端执行 `python3 scripts/backup_data.py --project-root /root/deeptutor`
3. 远程执行 `scripts/server_bootstrap_aliyun.sh`
4. 若 `.env` 缺失则自动生成模板
5. 若 `.env` 已存在则执行 `docker compose up -d --build`
6. 回到本地发起端执行 `scripts/verify_aliyun_public_endpoints.sh`，默认固定校验 `https://test2.yousenjiaoyu.com/`、`/healthz`、`/readyz`
7. 紧接着执行 `scripts/verify_aliyun_observability.sh`，通过 SSH/localhost 验证 `/metrics` 与 `/metrics/prometheus`

这条是“完整部署”路径，适用于：

- 第一次上线
- 修改了 `Dockerfile`
- 修改了 `requirements*.txt`
- 修改了前端构建产物或 Node 依赖
- 需要重新安装系统依赖

### 4. 访问地址

- 公网入口：<https://test2.yousenjiaoyu.com>
- 内部前端端口：<http://8.135.42.145:3782>
- 内部后端端口：<http://8.135.42.145:8001>
- 内部 API 文档：<http://8.135.42.145:8001/docs>

## 常用运维命令

SSH 到服务器后执行：

```bash
cd /root/deeptutor
docker compose ps
docker compose logs -f
docker compose restart
docker compose up -d --build
docker compose down
```

本地常用快捷入口：

```bash
# 仅重启现有容器，不发布代码
bash scripts/restart_aliyun.sh

# Python 后端 / Prompt / YAML 快速发布
PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/redeploy_aliyun_fast.sh

# 完整重建发布
PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/deploy_aliyun.sh
```

发布完成前，至少要看到这三条公网验收都通过：

```bash
curl -fsS https://test2.yousenjiaoyu.com/
curl -fsS https://test2.yousenjiaoyu.com/healthz
curl -fsS https://test2.yousenjiaoyu.com/readyz
```

Observability 验收不要打公网 `/metrics`。改用：

```bash
bash scripts/verify_aliyun_observability.sh
```

三条路径的区别：

- `restart_aliyun.sh`
  - 只做 `docker compose restart deeptutor`
  - 不同步代码，不重建镜像
  - 适合临时恢复服务
- `redeploy_aliyun_fast.sh`
  - 先 `rsync` 到服务器
  - 覆盖前先自动生成远端代码快照
  - 再执行远端发布环境校验
  - 再先执行一次远端 `python3 scripts/backup_data.py --project-root /root/deeptutor`
  - 再把 `deeptutor/` 等后端代码 `docker cp` 到正在运行的容器
  - 最后重启容器
  - 重启完成后，会先做一次公网域名探针验收，再做一次 observability 内网验收
  - 适合 Python 后端、Prompt、YAML、路由等无需重装依赖的改动
- `deploy_aliyun.sh`
  - 先同步，再执行 `docker compose up -d --build`
  - 覆盖前同样会先生成远端代码快照并校验远端发布环境
  - 同样会在真正重建前生成远端 runtime 备份
  - 远端重建完成后，会先做一次公网域名探针验收，再做一次 observability 内网验收
  - 最慢，但最完整
  - 适合依赖、Dockerfile、前端构建相关改动

### 代码回滚

如果这次发布需要回滚代码，而不是只恢复 `data/user` 运行态数据：

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/rollback_aliyun_release.sh latest
```

也可以指定某个 release id：

```bash
PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/rollback_aliyun_release.sh 20260422T120000Z_feature_branch_deadbeef1234
```

说明：

- 代码回滚会恢复最近一次远端代码快照，并重新执行 `server_bootstrap_aliyun.sh`
- 运行态数据不在这个脚本里回滚；如果要同时回滚 `data/user`，请配合 [docs/zh/guide/runtime-backup-restore.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/zh/guide/runtime-backup-restore.md)

## 当前部署建议

第一阶段后续验收与发布都统一用域名入口 `https://test2.yousenjiaoyu.com`，不要再用裸 IP 口径判断“是否上线成功”。端口 `3782/8001` 仅保留给 SSH 登录后的内部排障与 localhost 探针：

- 公网反代 authority 唯一
- 不再被裸 IP 超时误判
- 不影响 `/root/luban`

等你确认 `deeptutor` 成为主项目后，再切 nginx 域名反代。

## nginx 反代

如果后面要给 DeepTutor 单独域名，可以直接用 `deployment/aliyun/nginx/` 下的模板。

建议拆成两个域名：

- `deeptutor.example.com` -> `127.0.0.1:3782`
- `api.deeptutor.example.com` -> `127.0.0.1:8001`

然后把 `.env` 改成：

```dotenv
NEXT_PUBLIC_API_BASE_EXTERNAL=https://api.deeptutor.example.com
```

再重新启动：

```bash
cd /root/deeptutor
docker compose up -d --build
```

## 已知坑

### 1. 不要同步到 `/root/luban`

`/root/luban` 是现网项目目录，当前服务器已经在使用。`deeptutor` 必须单独放在 `/root/deeptutor`。

### 2. Docker 内不要把 Langfuse 指向 `localhost`

如果你在 `.env` 里写：

```dotenv
LANGFUSE_BASE_URL=http://localhost:3001
```

那容器内会把 `localhost` 当成容器自己，不是宿主机。

因此当前模板默认：

```dotenv
LANGFUSE_ENABLED=false
```

如果你要复用服务器现有 `/root/luban` 的 Langfuse：

```dotenv
LANGFUSE_ENABLED=true
LANGFUSE_BASE_URL=http://jgzk-langfuse:3000
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HTTPX_TRUST_ENV=false
LANGFUSE_TRACING_ENVIRONMENT=production
```

`scripts/server_bootstrap_aliyun.sh` 会在检测到 `luban_jgzk-network` 时自动叠加
`deployment/aliyun/docker-compose.langfuse.yml`，让 `deeptutor` 容器加入现有 Langfuse 网络。

### 3. `data/` 不参与上传

上传脚本默认排除 `data/`，目的是保护服务器上的：

- 用户数据
- 知识库
- 运行时日志

如果以后你要做数据迁移，不要直接改同步脚本，单独迁移更稳。

### 4. 为什么完整部署会慢

当前 `deploy_aliyun.sh` 走的是镜像重建，不是单纯重启。慢的主要原因通常是：

- Dockerfile 需要重新执行 `apt-get update/install`
- 需要重新安装 Python 依赖
- 阿里云服务器访问 Debian 官方源较慢
- 前端构建会重新执行 `npm ci` 和 `next build`
- 如果 Docker build cache 命中不充分，`python-base` 与 `production` 两个镜像层会分别下载系统依赖，看起来像“重复安装”

现在仓库已经补了阿里云默认镜像源和缓存挂载，但完整部署仍然会比“快速发布”慢很多。

不要把这些耗时误判为发布失败。判断发布是否完成，以最终事实为准：

```bash
ssh Aliyun-ECS-2 'cd /root/deeptutor && docker compose ps'
PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/verify_aliyun_public_endpoints.sh
bash scripts/verify_aliyun_observability.sh
```

### 5. 小程序 UI 改动不能只重启阿里云

`wx_miniprogram` 和 `yousenwebview/packageDeeptutor` 是微信小程序代码包，不是 DeepTutor Docker 容器运行时的一部分。阿里云重启只能更新后端/API、Web 前端和服务器上的仓库副本；真实手机里看到的小程序 UI 取决于微信开发者工具预览包或微信后台发布包。

因此如果修改的是小程序 WXML/WXSS/JS，例如聊天首页按钮、tab、输入框、卡片样式，必须按下面顺序验收：

1. 本地跑对应 Node contract 测试。
2. 用微信开发者工具打开 `yousenwebview`，进入 `packageDeeptutor/pages/chat/chat`，确认模拟器可见。
3. 如需真实手机立即看到，使用开发者工具重新生成真机预览码，或走微信上传/发版流程。
4. 如果小程序同时依赖后端新能力，再同步并重启阿里云后端。

不要把“阿里云仓库副本已有小程序代码”误报成“真实手机小程序 UI 已更新”。真实手机 UI 的 authority 是微信预览/发布包，不是 `/root/deeptutor` 里的源码。

### 6. 前端/小程序相关发布路径怎么选

发布脚本的适用范围必须先判断清楚：

- 只改 Python 后端、Prompt、YAML、路由，并且不涉及依赖：可以用 `redeploy_aliyun_fast.sh`。
- 改 Dockerfile、requirements、Web 前端构建产物、Node 依赖：必须用 `deploy_aliyun.sh` 或远端 `server_restart_aliyun.sh` 做完整镜像重建。
- 改 `wx_miniprogram` 或 `yousenwebview/packageDeeptutor`：阿里云同步只更新服务器源码副本；真实手机还必须重新预览或上传微信小程序包。

如果只是小程序 UI 改动，阿里云重启不是让真实手机 UI 更新的充分条件。只有当该 UI 调用了新的后端能力时，阿里云后端重启才是必要步骤。

### 7. 2026-05-12 联网按钮发布排障记录

本次现象：

- 本地微信开发者工具里能看到聊天首页“联网”按钮。
- 真实手机看不到该按钮。
- 用户追问是否同步到阿里云并重启服务。

根因：

- 本地 DevTools 使用本机源码。
- 真实手机使用微信预览/发布包。
- 阿里云 `/root/deeptutor` 当时仍是旧源码：`WEB_SEARCH_AVAILABLE=false`，且 WXML 中没有 `web-pill`。
- 前一轮只完成了本地改动和 DevTools 验证，没有同步到阿里云，也没有重启服务。

本次实际处理：

1. 远端只读核对 `/root/deeptutor`，确认旧代码仍存在。
2. 在 `/root/deeptutor/data/backups/` 下备份本次相关 8 个小程序文件。
3. 定向 `rsync` 覆盖到 `/root/deeptutor`，只写入 `/root/deeptutor` 内。
4. 远端核对 `WEB_SEARCH_AVAILABLE=true` 与 `web-pill` 已存在。
5. 执行完整 Docker build + recreate + restart。
6. 远端 `docker compose ps` 显示 `deeptutor` healthy。
7. `https://test2.yousenjiaoyu.com/`、`/healthz`、`/readyz` 公网验收最终通过。
8. 复测 `web_search("2026一建考试时间 官方通知")`，provider 为 `searxng`，能返回结果。

耗时原因：

- 为了符合写入边界，先备份再定向同步。
- 远端宿主机没有 `node`，不能直接跑小程序 Node 测试，只能用本地测试 + 远端文件内容校验替代。
- 小程序相关改动不是 Python fast reload 范畴，按运维手册应走完整镜像重建。
- 本次 Docker build cache 命中不充分，重新下载/安装 Debian、Rust、Python、Node 依赖。
- 公网域名探针前 18 次出现 DNS/连接/HTTP2 瞬时失败，最终第 19 次 frontend 通过，随后 `healthz/readyz` 通过。

经验教训：

- 汇报“已上线”前必须区分四个事实：本地源码、阿里云源码副本、阿里云容器运行态、微信小程序真实包。
- 小程序 UI 变更的终端验收不能用阿里云重启替代；必须重新预览或上传微信包。
- 同步阿里云前先读 `docs/zh/guide/aliyun-deploy.md`，确认该改动应走 fast reload、完整 deploy，还是微信小程序预览/上传。
- 远端服务健康只说明后端/API 可用；它不能证明真实手机 UI 已更新。
- 公网探针短暂失败不等于发布失败；以最终脚本完成状态和具体 endpoint 结果为准。

## 回滚步骤

如果发布后出现问题，先判断是“代码/镜像问题”还是“运行态数据问题”。

运行态回滚：

```bash
ssh Aliyun-ECS-2
cd /root/deeptutor
ls -lt data/backups | head
python3 scripts/restore_data.py --archive data/backups/deeptutor-data-user-YYYYmmdd-HHMMSSZ.tar.gz --project-root /root/deeptutor --replace
docker compose restart deeptutor
curl -sS http://127.0.0.1:8001/healthz
curl -sS http://127.0.0.1:8001/readyz
PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/verify_aliyun_public_endpoints.sh
bash scripts/verify_aliyun_observability.sh
```

代码版本回滚：

```bash
git checkout <上一个稳定提交>
bash scripts/deploy_aliyun.sh
```

不要把“代码版本回滚”和“运行态数据回滚”混成一步；先判断是哪一层出问题，再分别执行。
