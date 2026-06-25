# 阿里云 ECS 部署（8.135.42.145）

这份说明对应当前主服务器 `8.135.42.145`，部署目录固定为 `/root/deeptutor`。

## 发布硬护栏

- 每次执行阿里云 rebuild、redeploy、restart、hot patch 前，必须先重新阅读本 runbook；不要只凭上一次记忆、发布脚本名或远端当前状态操作。
- SSH 写入铁律：DeepTutor 在阿里云上只允许修改 `Aliyun-ECS-2:/root/deeptutor` 目录内的文件内容，其他路径一概不允许修改。
- 任何远端写操作，包括 `ssh` 内命令、`rsync`、`scp`、`docker cp`、热修、备份、回滚、部署脚本、临时验证产物，目标路径都必须落在 `/root/deeptutor` 内；不得用 `/tmp`、`/root`、`/root/luban` 或系统目录做绕行写入。
- `/root/luban`、`/etc`、`/usr`、`/var`、`/opt`、`/home`、nginx 系统配置、systemd、全局 cron、宿主机 Docker 配置等非 `/root/deeptutor` 路径全部视为只读观察面；只能读，不能创建、编辑、删除、移动、覆盖、改权限或安装依赖。
- 如果一次修复确实需要 `/root/deeptutor` 之外的宿主机改动，必须停止发布流程，先单独向用户说明目标路径、必要性、风险和替代方案；未获得新的明确授权前，一律不改。
- 默认只允许从干净候选分支发布；`main` 或 dirty tree 会被 [scripts/sync_to_aliyun.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/sync_to_aliyun.sh) 直接拒绝。
- 只允许发往 `Aliyun-ECS-2:/root/deeptutor`；发布脚本不提供非 canonical 主机或目录绕过开关。
- [scripts/sync_to_aliyun.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/sync_to_aliyun.sh) 每次覆盖远端前都会先生成代码快照 `data/releases/code/<release_id>.tar.gz`。
- [scripts/deploy_aliyun.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/deploy_aliyun.sh) 和 [scripts/redeploy_aliyun_fast.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/redeploy_aliyun_fast.sh) 在远端重启前都会先执行 `python3 scripts/backup_data.py`，自动生成本次发布的 runtime rollback 基线。
- 发布完成的唯一公网验收口径是：本地发起端对 `https://test2.yousenjiaoyu.com` 的 `front page`、`/healthz`、`/readyz` 探针全部通过；`docker compose ps` 或远端 `127.0.0.1` 只能算内部就绪，不能直接当成“已上线”。
- Observability 默认不走公网暴露；阿里云生产环境统一通过 SSH/localhost 抓取 `/metrics` 与 `/metrics/prometheus`。
- 发布前必须先判断改动类型。只改 Python 后端、Prompt、YAML、路由且不涉及依赖时，优先走 `redeploy_aliyun_fast.sh`；不要手工在远端直接跑 `docker compose up -d --build deeptutor`。
- 日常小程序同步不是完整部署。只改 `yousenwebview/packageDeeptutor/**`、`yousenwebview/app.js`、`yousenwebview/app.json`、`yousenwebview/app.wxss`、`yousenwebview/project.config.json`、`yousenwebview/sitemap.json`、`yousenwebview/tests/**` 或 `docs/**` 时，只运行 `ALLOW_MAIN_BRANCH_DEPLOY=1 bash scripts/sync_to_aliyun.sh once`，再按需要走微信 DevTools 预览/上传；不要运行 `deploy_aliyun.sh`，也不要触发 Docker rebuild。
- [scripts/deploy_aliyun.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/deploy_aliyun.sh) 会在完整重建前读取远端 `.env` 的 `DEEPTUTOR_GIT_SHA` 并计算 diff；如果变更只包含文档/微信小程序源码/小程序测试，会拒绝重建。只有确认必须重建镜像时，才允许显式设置 `FORCE_FULL_REBUILD=1`。
- 如果本地当前工作区很脏，但要发布的是已经提交并 push 的特定 commit，先从目标 commit 创建干净临时 worktree，再从该 worktree 执行同步/发布；不要在脏 `main` 上靠 `ALLOW_DIRTY_DEPLOY=1` 把无关文件一起带上阿里云。
- `git status` 干净、`DEEPTUTOR_GIT_DIRTY=false` 只证明 Git tracked surface 干净，不证明发布面干净。任何本地 dry-run、审计、测试生成的 ignored 目录，例如 `artifacts/`、`.gstack/`、`.local-runs/`，必须同时被 `sync_to_aliyun.sh`、deploy manifest hash 和 `.dockerignore` 排除；否则仍可能被 `rsync` 或 Docker build context 带到 `/root/deeptutor`。
- 紧急绕过护栏必须显式设置：
  - `ALLOW_DIRTY_DEPLOY=1`
  - `ALLOW_MAIN_BRANCH_DEPLOY=1`
  - 但远端写入根仍必须固定为 `Aliyun-ECS-2:/root/deeptutor`
- fail-closed 环境硬约束（2026-06-11 起，详见已知坑 #11）：`is_production_environment()` 把未设置 / 拼错 / `staging` 等一律按生产处理；生产 `.env` 必须配 `DEEPTUTOR_AUTH_SECRET` 和 `DEEPTUTOR_ATTEMPT_REF_SECRET`，否则启动或首次使用即失败。`validate_aliyun_release_env.sh` 会校验，但发布前应自行确认远端 `.env` 已含这两项。

建议发布前固定执行：

```bash
git branch --show-current
git status --short
git ls-files artifacts/
# protected 文件改动必须带本次 commit 的 changed files，否则测不出 domain 关系（见已知坑 #11）
python scripts/check_contract_guard.py $(git show --pretty= --name-only --first-parent HEAD)
FAIL_ON_NEW=1 bash scripts/ci/check_secure_routers.sh
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
- 会排除 `.env`、`data/`、`.git`、`.github`、`.gstack`、`.local-runs`、`.venv`、`node_modules`、`dist`、`artifacts`、测试报告和缓存目录
- 这样不会覆盖服务器上已经生成的数据和密钥
- 同步使用 checksum 比对，必须纠正远端源码漂移；不能只依赖时间戳判断文件是否需要覆盖。
- 如果同步日志里出现本地代理状态目录、QA 运行目录、dry-run 产物或构建产物目录，例如 `.gstack`、`.local-runs`、`artifacts`、`dist`，不要把它们留在 `/root/deeptutor`；先补 `sync_to_aliyun.sh` 的排除清单、manifest hash 排除口径和 `.dockerignore`，再只在 `/root/deeptutor` 内清理误传目录。

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
docker compose up -d --build  # 仅在确认需要完整镜像重建时使用
docker compose down
```

本地常用快捷入口：

```bash
# 仅重启现有容器，不发布代码
bash scripts/restart_aliyun.sh

# 日常小程序源码/文档同步，不重建容器
ALLOW_MAIN_BRANCH_DEPLOY=1 bash scripts/sync_to_aliyun.sh once

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

### Docker 日志与记录留存

如果要排查 Docker 高负载、Langfuse/ClickHouse 日志膨胀、或准备执行
`systemctl restart docker` 这类主机级操作，必须先把 Docker 日志和运行记录
留存在 `/root/deeptutor` 内，再重启或清理。不要把日志备份写到 `/tmp`、
`/root/luban`、`/var` 或其他系统目录。

当前统一留存位置：

- 文本目录：`/root/deeptutor/data/ops/docker-log-capture-<UTC timestamp>/`
- 压缩包：`/root/deeptutor/data/ops/docker-log-capture-<UTC timestamp>.tar.gz`
- 最新一次指针：`/root/deeptutor/data/ops/latest-docker-log-capture.txt`

2026-06-04 真实事故排查时的留存目录是：

- `/root/deeptutor/data/ops/docker-log-capture-20260604T031742Z`
- `/root/deeptutor/data/ops/docker-log-capture-20260604T031742Z.tar.gz`

该目录包含最近 24 小时的容器日志、`docker ps -a`、`docker stats`、
`docker inspect`、`docker events` 和 Docker 磁盘状态。本次原始文本约 504M，
压缩后约 16M；最大文件是 `jgzk-langfuse-clickhouse` 的最近 24 小时日志。

推荐捕获命令：

```bash
cd /root/deeptutor
ts=$(date -u +%Y%m%dT%H%M%SZ)
out="data/ops/docker-log-capture-$ts"
mkdir -p "$out/logs" "$out/inspect"
echo "$out" > data/ops/latest-docker-log-capture.txt

{
  date
  hostname
  uptime
  df -hT
  docker system df
  docker ps -a --no-trunc
} > "$out/00-host-and-docker-state.txt" 2>&1

docker stats --no-stream > "$out/01-docker-stats.txt" 2>&1 || true
docker events --since 24h --until 0s > "$out/02-docker-events-last-24h.txt" 2>&1 || true

for c in $(docker ps -a --format "{{.Names}}"); do
  safe=$(printf "%s" "$c" | tr "/ " "__")
  docker inspect "$c" > "$out/inspect/$safe.inspect.json" 2>&1 || true
  docker logs --since 24h "$c" > "$out/logs/$safe.last-24h.stdout-stderr.txt" 2>&1 || true
done

find "$out" -type f -printf "%s %p\n" | sort -nr > "$out/99-file-sizes.txt"
tar -czf "$out.tar.gz" -C "$(dirname "$out")" "$(basename "$out")"
du -sh "$out" "$out.tar.gz"
```

只有确认上面的文本目录和压缩包都存在后，才执行 Docker 重启、日志截断、
`docker system prune` 或 Langfuse 降载操作。Docker 重启后还要重新确认
`deeptutor` 容器进入 `healthy`，并从本地发起端验证公网 `/healthz` 与
`/readyz`。

如果本次发布前本地生成过 ignored 产物，还要确认它们没有进入远端发布面：

```bash
ssh Aliyun-ECS-2 'test ! -e /root/deeptutor/artifacts && echo remote_artifacts_absent'
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
  - 再执行远端 `docker compose build deeptutor`
  - 再 `docker compose up -d --no-deps --force-recreate deeptutor`，用新镜像刷新 `.env` release lineage
  - 重启完成后，会先做一次公网域名探针验收，再做一次 observability 内网验收
  - 适合 Python 后端、Prompt、YAML、TutorBot skill 资产等不需要前端构建或部署拓扑变化的候选；若触碰 `Dockerfile`、`requirements*`、`pyproject.toml`、`web/`、`wx_miniprogram/`、`yousenwebview/` 或部署 compose 面，脚本会拒绝，必须改用 `deploy_aliyun.sh`
- `deploy_aliyun.sh`
  - 先同步，再执行 `docker compose up -d --build`
  - 覆盖前同样会先生成远端代码快照并校验远端发布环境
  - 同样会在真正重建前生成远端 runtime 备份
  - 远端重建完成后，会先做一次公网域名探针验收，再做一次 observability 内网验收
  - 最慢，但最完整
  - 适合依赖、Dockerfile、前端构建相关改动

### 2026-06-15/16 快速发布性能教训：fast path 不得热补丁容器

本次只改 Python 后端逻辑（Nexus 案例题输出与评分 ctx），第二次同步日志已经显示
`Number of files transferred: 0`，说明源码没有重复全量上传；真正耗时来自
`redeploy_aliyun_fast.sh` 仍会执行 `docker compose ... build deeptutor`。只要 Docker
缓存没有完整命中，`python-base` / `production` 层就可能重新下载 Debian、Rust、Python
runtime.lock 依赖，看起来像“又全部重新下”。

曾短暂评估过 `--no-build` + 容器内代码刷新作为性能优化，但该路径会让 `/root/deeptutor`
源码、镜像内容、运行容器 `/app` 变成三份 truth；上线发布链必须优先保持单一 release
truth，因此 `server_fast_reload_aliyun.sh` 不再执行 `docker cp` 热补丁。

现行规则：

- `sync_to_aliyun.sh` 负责代码面，通常很快；不要把 `rsync` 日志里的文件列表误读成全量上传。
- `redeploy_aliyun_fast.sh` 是后端候选快路径：同步代码、注入 release lineage、运行态备份、重建 `deeptutor` 服务镜像，再 force-recreate 容器。
- 容器 `/app` 不是 `/root/deeptutor` 的 bind mount；只 rsync 到宿主机不会让运行时代码生效。fast path 必须通过 `server_fast_reload_aliyun.sh` 的镜像 build + force-recreate 生效，禁止手工 `docker cp` 热补丁。
- fast path 只允许后端运行时代码面：`deeptutor/`、`deeptutor_cli/`、`contracts/`、`scripts/`、`schemas/`；依赖或构建链变化必须走完整发布。
- 触碰 `Dockerfile`、`requirements*`、`pyproject.toml`、`web/`、`wx_miniprogram/`、`yousenwebview/`、部署 compose 面或 Node/package 锁文件时，`redeploy_aliyun_fast.sh` 必须拒绝，改走 `deploy_aliyun.sh`。
- fast path 仍必须保留 `/root/deeptutor` 代码快照、runtime 备份、host/container SHA 对齐、公网 `/healthz` `/readyz`、observability 验收；不能用“快”绕过 release truth。
- SSH 断开（`Connection reset by peer` / `Broken pipe`）不等于远端 build 停止。必须先只读检查
  `docker compose --progress plain ... build`、`buildkit/executor`、容器 SHA 和 `/root/deeptutor/.env`
  SHA，再决定是否重跑。
- 多个本地窗口/agent 同时同步或部署同一台阿里云，会共享 Docker build cache、镜像 tag、容器名
  `deeptutor`，可能互相拖慢或最后由后完成的一路覆盖前一路。发布前先查远端是否已有 build/deploy
  进程；发现已有进程时只轮询等待，不要启动第二个 deploy。

后续优化方向（需要单独实现成正式脚本和 runbook，不得临时手工热补丁）：

- 增加远端发布锁：在 `/root/deeptutor/data/ops/` 下记录当前 deploy pid、目标 SHA、开始时间和
  owner。锁存在且进程仍活跃时，新发布默认拒绝或进入只读等待模式。

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

### 7. 后端小改动误走完整 build 怎么止损

如果一次 Python 后端小改动误触发了远端完整镜像重建，先不要继续叠加新的发布动作。按下面顺序收敛：

2026-05-18 的一次真实教训是：只改 Python/RAG 合成逻辑时，没有先读本 runbook，而是只看了脚本和 `docker compose`，于是手工触发了完整 build。阿里云侧 Debian 下载很慢，`apt-get` 阶段长时间卡住，最后只能停止 build，再用更窄的同步和容器重启路径恢复验证。以后遇到同类后端小改动，默认先走 `redeploy_aliyun_fast.sh`；只有依赖、Dockerfile、Web 前端构建或 Node 依赖变化时，才启动完整 build。

1. 确认旧线上容器是否仍然 healthy：

```bash
ssh Aliyun-ECS-2 'cd /root/deeptutor && docker ps --format "{{.Names}} {{.Status}}" | grep deeptutor || true'
```

2. 确认是否还有后台 build / pip / rustup 进程：

```bash
ssh Aliyun-ECS-2 'ps -ef | grep -E "docker compose up -d --build deeptutor|pip install -r requirements.txt|rustup|apt-get" | grep -v grep || true'
```

3. 如果确认只是误选发布路径，且旧容器仍 healthy，可以停止这次未完成 build：

```bash
ssh Aliyun-ECS-2 'kill <docker-compose-pid> <child-pid> 2>/dev/null || true'
```

4. 停止后重新核对旧容器健康，不要把中断 build 误判为线上失败：

```bash
ssh Aliyun-ECS-2 'cd /root/deeptutor && docker ps --format "{{.Names}} {{.Status}}" | grep deeptutor || true'
```

5. 回到本地，按正式快速发布脚本重新发布：

```bash
PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/redeploy_aliyun_fast.sh
```

注意三条判断：

- 远端 `/root/deeptutor` 源码已经同步，只能说明服务器源码副本更新；不能说明运行中容器已经加载新代码。
- 容器里的 `/app/...` 代码来自镜像层，不是 `/root/deeptutor` 的 bind mount；只有发布脚本完成重建/重载并通过公网验收，才能说已上线。
- 不要用 `docker cp` 热补丁当常规发布路径；只有明确紧急权衡时才可临时使用，并且最终仍要回到发布脚本收敛镜像内容。
- 如果看似必须用 `docker cp` 直接修改运行中容器，先停止发布流程，向用户说明为什么发布脚本无法解决、目标容器路径、风险和回收计划；未获得新的明确授权前不要执行。即使获得授权，也必须把它汇报为临时止血路径，并在事后回到 `/root/deeptutor` 下的正式发布脚本收敛镜像内容。

### 8. 2026-05-12 联网按钮历史排障记录

以下是一次历史排障记录，用来说明发布边界，不代表当前线上一定已经运行最新 commit。每次上线仍必须重新核对容器 `DEEPTUTOR_GIT_SHA`、公网 endpoint 和微信预览/发布包。

当时现象：

- 本地微信开发者工具里能看到聊天首页“联网”按钮。
- 真实手机看不到该按钮。
- 用户追问是否同步到阿里云并重启服务。

根因：

- 本地 DevTools 使用本机源码。
- 真实手机使用微信预览/发布包。
- 阿里云 `/root/deeptutor` 当时仍是旧源码：`WEB_SEARCH_AVAILABLE=false`，且 WXML 中没有 `web-pill`。
- 前一轮只完成了本地改动和 DevTools 验证，没有同步到阿里云，也没有重启服务。

当时处理：

1. 远端只读核对 `/root/deeptutor`，确认旧代码仍存在。
2. 在 `/root/deeptutor/data/backups/` 下备份本次相关 8 个小程序文件。
3. 定向 `rsync` 覆盖到 `/root/deeptutor`，只写入 `/root/deeptutor` 内。
4. 远端核对小程序源码中的联网按钮实现已存在。
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

### 8. 2026-05-06 完整部署排障记录

这次从本地同步 `codex/upstream-absorb-v135` 到阿里云并重启时，没有先看到业务代码启动失败；主要现象是完整镜像重建耗时明显。

已确认的发布链路事实：

- 本地提交：`2065e86a112a61360b5ed8a40d1bc19f2fc15e77`
- 远端目标：`Aliyun-ECS-2:/root/deeptutor`
- 发布命令：`PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/deploy_aliyun.sh`
- 远端发布环境校验通过，`SERVICE_ENV=production`、`APP_ENV=production`、`DEEPTUTOR_GIT_DIRTY=false`
- 重建前 runtime 数据备份成功，备份目录为 `/root/deeptutor/data/backups/`
- 自动检测到共享 Langfuse 网络 `luban_jgzk-network`

本次遇到的信号和判断：

| 信号 | 是否阻断 | 判断 | 下次处理 |
| --- | --- | --- | --- |
| `rsync` 提示 `cannot delete non-empty directory: web-deploy` | 否，除非后续构建或静态资源校验失败 | 远端遗留 `web-deploy` 目录非空，`rsync --delete` 没删掉该目录，但源码同步继续完成 | 如果公网前端静态资源异常，再 SSH 执行 `rm -rf /root/deeptutor/web-deploy` 后重跑部署；不要在无症状时把它当发布失败 |
| 前端构建出现 `npm audit` 漏洞数量提示 | 否 | 这是依赖安全审计提示，不等于 Next.js 构建失败；本次 Next production build 已继续执行 | 单独安排依赖审计，不要在发布窗口中临时升级大批前端依赖 |
| Docker build 长时间停在 `pip install -r requirements.txt` | 否，除非最终超时或 pip 报错退出 | 完整部署会重新安装 Python 依赖，且大包如 PyMuPDF、numpy、LLM/agent 依赖下载耗时明显 | 先继续等待；如果 10 分钟以上无输出，再看 Docker build 日志、网络、磁盘；不要误判为服务已挂 |
| `docker compose` 提示 orphan containers: `deeptutor-searxng`、`deeptutor-valkey` | 否 | 这些是当前 compose 项目下仍在运行但本次 compose 文件未直接管理的旧服务；本次 `deeptutor` 容器已正常重建 | 只有确认这些服务已无依赖时，才执行 `docker compose up -d --remove-orphans`；不要在发布窗口里顺手清理 |
| 公网前端探针前几次返回 502 | 否，若后续重试通过 | 新容器刚启动时 health 仍是 `starting`，Nginx/上游短时间不可用是可接受启动窗口 | 以脚本 20 次重试的最终结果为准；若持续 502，再看 `docker compose ps deeptutor`、`docker compose logs --tail=200 deeptutor` 和宿主 Nginx upstream |

排查时按这个顺序收敛：

```bash
# 1. 看发布脚本是否还在输出，先不要中断仍在下载依赖的 build
PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/deploy_aliyun.sh

# 2. 如果脚本失败，再看容器状态
ssh Aliyun-ECS-2 "cd /root/deeptutor && docker compose ps && docker compose logs --tail=200 deeptutor"

# 3. 如果只是 web-deploy 遗留目录影响静态资源，再清理后重跑完整部署
ssh Aliyun-ECS-2 "rm -rf /root/deeptutor/web-deploy"
PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/deploy_aliyun.sh

# 4. 如果代码未改依赖、Dockerfile、前端构建，优先走快速发布，避免整镜像重建
PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/redeploy_aliyun_fast.sh
```

完成判断不能只看 `docker compose up -d` 返回。必须同时满足：

```bash
ssh Aliyun-ECS-2 "cd /root/deeptutor && docker compose ps deeptutor"
curl -fsS https://test2.yousenjiaoyu.com/
curl -fsS https://test2.yousenjiaoyu.com/healthz
curl -fsS https://test2.yousenjiaoyu.com/readyz
bash scripts/verify_aliyun_observability.sh
```

### 9. 2026-05-20 主干合并后完整部署记录

这次是在 `origin/main` 已经更新到 `67744094d080790e93672316dd0c9a139f661d9c` 后，按用户要求从本地同步到阿里云并重启服务。

已确认的发布链路事实：

- 本地 `HEAD`、`main`、`origin/main` 都指向同一个 commit：`67744094d080790e93672316dd0c9a139f661d9c`
- 当前本地可见分支名可能仍是临时分支，例如 `qa-followup-20260520`；发布判断不能只看分支名，必须同时核对 `git rev-parse HEAD main origin/main`
- 发布命令使用：`ALLOW_MAIN_BRANCH_DEPLOY=1 PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/deploy_aliyun.sh`
- 远端目标仍固定为 `Aliyun-ECS-2:/root/deeptutor`
- 远端 release lineage：`1.0.0+67744094d080790e93672316dd0c9a139f661d9c+production`
- 重建前 runtime 数据备份成功：`/root/deeptutor/data/backups/deeptutor-data-user-20260519-165805Z.tar.gz`
- 公网验收最终通过：`/`、`/healthz`、`/readyz`
- Observability 内网验收通过，`langfuse_connectivity=jgzk-langfuse:3000 reachable`

本次新增经验：

| 信号 | 是否阻断 | 判断 | 下次处理 |
| --- | --- | --- | --- |
| `rsync` 把 `.gstack`、`.local-runs` 或 `web/.gstack` 传到 `/root/deeptutor` | 不直接阻断当前容器启动，但必须修 | 这是本地 agent/QA 状态污染远端源码副本，不属于生产代码或运行态数据 | 先补 `scripts/sync_to_aliyun.sh` 的 `EXCLUDES`、manifest hash 排除清单和 watch 排除规则；再只在 `/root/deeptutor` 内清理误传目录；不要去 `/tmp`、`/root` 或系统目录绕行 |
| 本地分支名不是 `main`，但 `HEAD == main == origin/main` | 不阻断 | 合并后 Codex 工作区可能还停在临时分支名上，但提交指针已经与主干一致 | 发布前同时跑 `git rev-parse HEAD main origin/main`，不要只凭 `git branch --show-current` 判断是否发布了正确 commit |
| 公网前端探针前两次返回 502，第三次通过 | 不阻断，若后续重试通过 | 新容器刚启动时 Docker health 仍处于 `starting`，公网反代短暂 502 是可接受启动窗口 | 以 `verify_aliyun_public_endpoints.sh` 的最终结果为准；若 20 次内仍失败，再看容器状态和日志 |
| `docker compose ps` 显示 `health: starting`，但 `/readyz` 已通过 | 不阻断，但要继续复核 | Docker health 与应用 ready endpoint 存在短暂时间差 | 等容器进入 `healthy`，并同时保留公网 `/readyz`、内网 observability 结果作为完成证据 |

本次清理命令必须保持在 `/root/deeptutor` 内：

```bash
ssh Aliyun-ECS-2 'cd /root/deeptutor && find . -maxdepth 3 \( -name .gstack -o -name .local-runs \) -type d -print -exec du -sh {} \;'
ssh Aliyun-ECS-2 'cd /root/deeptutor && rm -rf ./.gstack ./.local-runs ./web/.gstack'
```

完成判断仍按四个层面收口：

```bash
git rev-parse HEAD main origin/main
ssh Aliyun-ECS-2 "cd /root/deeptutor && docker compose ps deeptutor"
PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/verify_aliyun_public_endpoints.sh
bash scripts/verify_aliyun_observability.sh
```

### 10. 2026-05-25 ignored artifacts 误入发布面

这次在干净候选分支发布 `99a5183bd680f1292c12f749f2c6c9b32c4cb7a4` 时，本地 `artifacts/assessment_testset/...` 是 gitignored 的审计产物，`git status` 仍然干净，远端 `.env` 也显示 `DEEPTUTOR_GIT_DIRTY=false`。但发布脚本当时只排除了 Git 和常见缓存目录，没有排除 `artifacts/`，所以第一次同步把这些本地审计产物带进了 `/root/deeptutor/artifacts`，Docker build context 也随之增大。

根因不是某个 assessment 目录本身，而是发布链路把“Git clean”误当成“release surface clean”。Git 是否跟踪、rsync 是否上传、Docker build context 是否包含，是三套边界，必须同时收口。

已采取的脚本侧修复：

- `scripts/sync_to_aliyun.sh` 的 `EXCLUDES` 增加 `artifacts`。
- deploy manifest hash 的 `excluded_names` 增加 `artifacts`，避免 ignored 产物影响发布清单。
- `clean_remote_deploy_noise()` 增加 `artifacts`，只在 `/root/deeptutor` 内清理历史误传目录。
- `.dockerignore` 增加 `artifacts/`，避免审计产物进入 Docker build context。

下次遇到同类情况，先做这组判断：

```bash
git status --short --untracked-files=all
git ls-files artifacts/
git check-ignore artifacts 2>/dev/null || true
ssh Aliyun-ECS-2 'test ! -e /root/deeptutor/artifacts && echo remote_artifacts_absent'
```

判断规则：

- `git ls-files artifacts/` 必须为空；如果不为空，说明产物已经进入 Git tracked surface，必须先停下处理。
- `git check-ignore artifacts` 只能证明 Git 会忽略它，不能证明发布脚本会忽略它。
- 如果远端已经出现 `/root/deeptutor/artifacts`，清理命令只能写 `/root/deeptutor` 内；不得为了临时中转或备份写 `/tmp`、`/root/luban`、`/var` 或系统目录。
- 清理后必须重新发布并确认 Docker build context 回落到合理体量；不要只删远端目录后直接宣布上线完成。

### 11. 2026-06-11 fail-closed 环境 + CI 门连锁（上线前根因加固复盘）

这次上线前根因加固把 `is_production_environment()` 改成 **fail-closed**：只有显式声明为 `local/dev/development/test/testing/ci/eval` 才算非生产；**未设置 / 拼错 / `staging` / 未知值一律按生产处理**，dev 后门默认关闭。配套两条运维硬约束：

- 生产（含任何非上述白名单环境，包括 env 漏设的情况）**必须配置 `DEEPTUTOR_AUTH_SECRET` 和 `DEEPTUTOR_ATTEMPT_REF_SECRET`**。缺 `DEEPTUTOR_AUTH_SECRET` 启动即拒；缺 `DEEPTUTOR_ATTEMPT_REF_SECRET` 在首次签 attempt ref 时拒（不再回落 dev 默认值）。`redeploy_aliyun_fast.sh` 已在重启前跑 `validate_aliyun_release_env.sh`，本次发布日志确认 `SERVICE_ENV=production`、`APP_ENV=production` 且校验通过。
- 这意味着 fail-closed 把“env 漏设”从“后门敞开”变成“按生产收紧”。代价是：本地 / CI / DevTools QA 必须显式 `export DEEPTUTOR_ENV=local`（pytest 由 `tests/conftest.py` 模块级 `setdefault` 自动钉成 `local`）。

两个直接踩到的坑：

- **import 期副作用 + fail-closed 会炸裸 import。** `attempt_refs.py` 原本在 import 时跑 `_log_secret_fingerprint() -> _secret()`。fail-closed 下未设环境=生产、又没 secret，于是 CI 的 “Import Check”（裸 `python -c "import deeptutor.api.routers.unified_ws"`，无 `.env`、无 secret）在 import 阶段就 `RuntimeError` 崩溃，CLI 工具 / 脚本同样会崩。根因是“import 期可 raise 的副作用”，不是 fail-closed 本身。修法是**把强制延迟到使用时**：import 期诊断容忍缺 secret（只告警），`_secret()` 真正签名 / 校验时仍 fail-closed。本地能蒙混是因为开发机 `.env` 带 `SERVICE_ENV=development`，`env_store.load()` 会把它 `setdefault` 进 `os.environ`，让 `runtime_environment()` 误判非生产——这也是测试里要 `monkeypatch.setenv("DEEPTUTOR_ENV","production")` 才稳的原因。
- **改 protected 文件会触发一连串 contract-guard / CI 门**，逐个被前一个门遮住，容易打地鼠。这次的连锁是：`contract_guard`（改 `unified_ws.py`/`attempt_refs.py` 这类 protected 文件，commit 必须同时含该 domain 已登记的测试——新测试要先登记进 `contracts/index.yaml` 的 `domains.<域>.test_files`，并 re-mirror 到 `deeptutor/contracts/index.yaml`）→ `Secure router fail-on-new`（新增 import 会移动 bare `APIRouter()` 行号，要刷新 `scripts/ci/baselines/secure_routers_baseline.txt`）→ `Import Check`（见上一条）。

下次改动后端再发布前，按这组顺序本地自检，避免 push 上去才发现 main 变红：

```bash
# 1) contract-guard 要带本次 commit 的 changed files（不带参数测不出 protected/domain 关系）
python3 scripts/check_contract_guard.py $(git show --pretty= --name-only --first-parent HEAD)
# 2) secure-router 基线（加了 import 就可能要刷行号）
FAIL_ON_NEW=1 bash scripts/ci/check_secure_routers.sh
# 3) NameError / undefined-name 门
ruff check --select F821,F811 deeptutor deeptutor_cli scripts
# 4) Import Check：在 fail-closed 生产口径下裸 import 不能崩
env -u DEEPTUTOR_ATTEMPT_REF_SECRET DEEPTUTOR_ENV=production python3 -c \
  "from deeptutor.api.routers.unified_ws import unified_websocket; print('import OK')"
```

另外两条运维事实记录：

- `redeploy_aliyun_fast.sh` 同步的是**本地工作树**（不是 `origin/main`），且 `--delete` 镜像代码面。`.env*`、`.secrets*`、`data`、`artifacts`、`tmp`、`*.log` 已排除，生产配置 / 数据 / 上传文件安全；但脏 `main` 上 `ALLOW_DIRTY_DEPLOY=1` 会把未提交的无关文件（如别人并发在写的 `docs/`）一并带上生产。优先按 §发布硬护栏 用干净 worktree。
- GitHub `Deploy Gate` workflow 长期 9–10s 快速失败，且早于本次改动就存在（与代码无关）；判断 main CI 是否因本次改动变红，看 `Tests` workflow 的具体 job，不要被 `Deploy Gate` 误导。

### 12. 2026-06-11 detached HEAD 禁止发布 + 并发发布撞车

这次想用“干净 worktree 发布”避免脏 `main` 把无关改动带上生产（§发布硬护栏 §19），于是 `git worktree add --detach <sha>` 建了一个游离（detached HEAD，只指向某个 commit、不在任何分支上）的 worktree，结果 `sync_to_aliyun.sh` 直接拒绝：

```
无法识别当前分支；禁止在 detached HEAD 直接发布。
```

根因不是 bug，而是发布要可追溯：release_id / lineage 需要一个分支名来记录“这次是从哪条线发的”。游离 HEAD 没有分支名，发布记录无法定位来源，所以脚本干脆禁止。

正确做法是从目标 commit 检出一个**具名分支**再发布，而不是游离 HEAD：

```bash
# 推荐：建 worktree 时直接给一个临时具名分支
git worktree add /tmp/deploy-snapshot -b deploy-<shortsha> origin/main
# 或：已经建成 detached worktree，进去补一个分支
cd /tmp/deploy-snapshot && git checkout -b deploy-<shortsha>
```

分支名只要不是 `main` 就同时满足两条护栏：detached 护栏（要有分支名）和“禁止从 `main` 直发”护栏（分支名 ≠ `main`）。worktree 是干净的就不用加 `ALLOW_DIRTY_DEPLOY`。用完记得 `git worktree remove <path>` 并删临时分支。

同日还撞到**并发发布**：两个发布进程同时对同一台阿里云发布，一个在发 `d59cd37c`、另一个在发更新的 `be971a14`，期间长时间 docker build 把 SSH 拖断（`Connection reset by peer` / `Broken pipe`，脚本 `EXIT 255`）。教训：

- **同一时间只允许一条发布在跑。** 发布前先确认没有别的发布在进行：看 `data/releases/code/` 里最新 manifest 的时间戳、`docker compose ps` 容器创建时间、`.env` 的 `DEEPTUTOR_GIT_SHA`，确认它们指向你预期的版本。
- **SSH 在长 build 中途断不会停机。** `up -d --force-recreate` 在 build 之后才跑；build 被打断时旧容器继续服务（本次公网 `front/healthz/readyz` 全程 200），但磁盘可能停在“已同步新代码、容器仍是旧镜像”的半同步状态，需要重新发布对齐。
- **并发覆盖会自愈但要核对。** 本次一个进程把磁盘 rsync 回了旧 `d59cd37c`，又被另一个进程的 `be971a14` 发布重新同步盖回——靠 manifest 时间戳 + 磁盘 sentinel 文件 md5 才能确认最终落到哪个版本。多人/多 agent 共同发布时，发布后必须用这两样东西核对最终状态，不能假设“我发的就是最后生效的”。

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

### 13. 2026-06-12 prompt 资产发布耗时复盘（两次部署才闭环）

这次只改了 TutorBot skill prompt 资产 + 一处 `_SCENE_REFERENCE_FILES` 注入，本应一次 `redeploy_aliyun_fast.sh` 闭环，实际多花了一倍时间。根因和规则：

| 信号 | 是否阻断 | 根因 | 下次处理 |
| --- | --- | --- | --- |
| 脚本拒绝："禁止直接从 main 发布" | 阻断 | 在脏 main 工作区直接跑发布脚本，没有先建干净候选分支 | 发布前第一步就建干净 worktree（`git worktree add /tmp/deeptutor-release-<sha> <sha> -b release/<topic>`），不要先试脏 main 再被脚本打回 |
| 首次部署后远端 `contract_guard` readiness FAIL | 阻断（required gate） | `question_lifecycle_skills.py` 是 contract-sensitive 文件，commit 集里没有同步更新 contract surface。本地无参跑 `check_contract_guard.py` 通过是**假阴性**：脏工作树里恰好有别的 contracts 改动掩蔽了要求 | 发布前用真实变更集跑：`python scripts/check_contract_guard.py $(git diff --name-only origin/main..HEAD)`。contract-sensitive 文件改动必须与 contract surface 更新在同一个发布集里，否则远端 readiness 必 FAIL，要二次 commit + 二次部署 |
| 修 contract 文件时工作树同文件有他人脏改动 | 不阻断但易夹带 | 直接 `git add` 会把无关脏 hunk 一起带进发布 | 用 `git show :file` 取 index 版本插入自己的行，`git hash-object -w` + `git update-index --cacheinfo` 只 stage 自己的 hunk；工作树副本另行同步插入保持一致 |

通用结论：**prompt/skill 资产改动如果触碰了任何 contract-sensitive 的注入/路由代码，发布成本就从"快速重启"升级为"contract 闭环 + 快速重启"**。预估工时时按后者算，并在 commit 前就把 contract 条款补齐，避免部署后被远端 readiness gate 打回重来。

### 14. 2026-06-14 SSH 断开先三查别盲目重跑 + 并行进程把超集 push 到 origin/main

§12 讲了并发发布撞车 + SSH 长 build 断开会留下半同步态。这次补两个 §12 没覆盖的角度，核心是：**SSH 断开 ≠ 你的部署失败，盲目重跑才是真危险**。

1. **SSH 断开后先三查，再决定动不动。** 远端 Next.js build ~6.5min，静默期连接常被 reset（`Connection reset by peer`/`Broken pipe`）。不要立刻重跑发布脚本——重跑会与在飞的并行 build 撞同一容器 = 损坏。先查：
   - 远端构建进程：`ssh Aliyun-ECS-2 "ps aux | grep -E 'next build|up -d --build|buildkit/executor' | grep -v grep"`
   - `origin/main` SHA：`git fetch origin main && git rev-parse origin/main`——并行进程可能在你 push 后又把超集推过你。
   - 容器 SHA + 容器内代码：`docker inspect deeptutor --format '{{range .Config.Env}}{{println .}}{{end}}' | grep DEEPTUTOR_GIT_SHA`，再 `docker compose -f /root/deeptutor/docker-compose.yml exec -T deeptutor grep -c '<你的新符号>' <改动文件>`。

2. **并行进程可能把"你的 main + 别的分支"合成超集 push 到 origin/main 并部署。** 本次：我 push 了我的 release（`e61b8fa37`），SSH 在远端 build 断开；排查发现另一进程把它 + feat 分支 + member-permission 合成 `08a697030`，push 到 origin/main 并部署。我的代码随它上线，`origin/main == host .env == container == 08a697030` 四层对齐——这是 **closed release，不是 drift**。判据：容器内你的新符号出现且**仅 1 次**（cherry-pick + merge 无重复）。

3. **等并行 build 落定用后台 `until` 轮询，不要前台 sleep、也不要重连重跑：**

   ```bash
   for i in $(seq 1 40); do
     P=$(ssh Aliyun-ECS-2 "ps aux|grep -E 'next build|up -d --build|buildkit/executor'|grep -v grep|wc -l"|tr -d ' ')
     [ "${P:-1}" = 0 ] && { ssh Aliyun-ECS-2 "docker inspect deeptutor --format '{{.Created}}'; docker inspect deeptutor --format '{{range .Config.Env}}{{println .}}{{end}}'|grep DEEPTUTOR_GIT_SHA"; break; }
     sleep 20
   done
   ```
   落定后跑正常 post-deploy 验证（host .env / container / 公网端点 / 可观测性四层）。

4. **要把生产 pin 到恰好你的 push（而非超集）= 回退并行 actor 的工作——先上报用户，绝不静默 undo 不属于你的部署。**

### 15. 2026-06-24 Langfuse 容器跨 docker 网络隔离 → trace 静默丢

**失败签名**：`verify_aliyun_observability.sh` 报 `Langfuse 容器内连通性失败: socket.gaierror: [Errno -2] Name or service not known`（容器内 `getaddrinfo('jgzk-langfuse')` 失败）。公网端点全绿、容器 healthy，**只有可观测这一层挂**。

**根因**：`LANGFUSE_BASE_URL=http://jgzk-langfuse:3000` 按 docker service 名解析。Langfuse 整套容器在跑（`jgzk-langfuse*` Up，healthy），但它在自己的 compose 网络 `luban_jgzk-network`，而 deeptutor 在 `deeptutor_deeptutor-network`——**两个 docker 网络隔离，deeptutor 解析不到对方的 service 名**。`LANGFUSE_ENABLED=true` 时 LLM trace 一直静默丢（`LANGFUSE_TIMEOUT_S=5` 优雅失败，不报错只丢数据）。

**诊断三连**（确认是网络隔离非 Langfuse 挂）：
```bash
ssh Aliyun-ECS-2 "docker ps | grep langfuse"                                   # Langfuse 容器在跑?
ssh Aliyun-ECS-2 "docker inspect jgzk-langfuse  --format '{{range \$k,\$v := .NetworkSettings.Networks}}{{println \$k}}{{end}}'"  # 它在哪个网络
ssh Aliyun-ECS-2 "docker inspect deeptutor      --format '{{range \$k,\$v := .NetworkSettings.Networks}}{{println \$k}}{{end}}'"  # deeptutor 在哪个网络 → 不同就是它
```

**修复（两层）**：
1. **即时**（运行时，重建即丢）：`ssh Aliyun-ECS-2 "docker network connect luban_jgzk-network deeptutor"` → 立刻 `langfuse_connectivity=...reachable`。
2. **durable**（`docker-compose.yml`，跨重建持久）：networks 段加 `luban_jgzk-network: { external: true }`，deeptutor service 的 networks 加 `- luban_jgzk-network`。⚠️ 改 `docker-compose.yml` 属 `FAST_RELOAD_BLOCKED`——**下次须走 `deploy_aliyun.sh` 全量部署**才把网络配置烤进容器；在那之前即时 connect 维持，期间若 fast-reload 重建容器会丢、需重连。

### 16. 2026-06-24 磁盘反复爆盘 → 容器写不了 /tmp 崩溃 → 502（多次部署后必现）

**失败签名**：公网 `502 Bad Gateway`（nginx），容器 `restarting / health=unhealthy / RestartCount` 持续涨；`docker compose logs deeptutor` 末尾是
```
FileNotFoundError: [Errno 2] No usable temporary directory found in ['/tmp', '/var/tmp', '/usr/tmp', '/app']
```
（supervisord 启动时 `tempfile.gettempdir()` 找不到可写临时目录）。`df -h /` 显示 **100% 已用 / 0 可用**。这不是代码 bug，是**磁盘满到容器连 /tmp 都写不了**。

**根因（为什么"老爆"）**：
1. **`server_fast_reload_aliyun.sh:49` 每次部署都跑 `docker compose build deeptutor`**——所谓"快速发布"**其实每次都 docker build 重建镜像**（名不副实），每次 build 生成 GB 级 **build cache 层**堆进 `/var/lib/docker`，**从不自动清理**。一个 session 连发 ~6 次 → 累积 **9GB+ build cache**（`docker builder prune -af` 实测一次清出 9.1GB）。
2. **基线本就紧**：Langfuse 数据卷（clickhouse+minio）**12.5GB 且随 trace 持续增长** + deeptutor 镜像 ~4.9GB + 仓库 `/root/deeptutor` ~14GB + `sync_to_aliyun.sh` 的 `RELEASE_KEEP=5` 个 release 快照，全压在 **99GB** 单盘上。基线长期 90%+。
3. 几次部署累积的 build cache（9GB）就把盘从 ~85% 顶到 100% → 容器重建/重启时写不了 /tmp → supervisord 崩 → 502。**rsync 大树（含 14G diagram/PDF）+ 每次 release 快照只会雪上加霜。**

**抢修三步（安全，只清未用，绝不碰 Langfuse 业务数据卷）**：
```bash
ssh Aliyun-ECS-2 "docker builder prune -af && docker image prune -af"   # 清 build cache + 未用镜像(在用的保留),实测一把回收 9~15G
ssh Aliyun-ECS-2 "df -h /"                                              # 确认有 >5G 空闲
ssh Aliyun-ECS-2 "cd /root/deeptutor && docker compose restart deeptutor"  # 有空间后容器即可正常起
curl -s -o /dev/null -w '%{http_code}\n' https://test2.yousenjiaoyu.com/   # 等几秒 → 200
```
> **红线**：14.3GB 的 `langfuse_langfuse_ch_data`(7.7G) + `langfuse_langfuse_minio_data`(6.6G) 是**生产 trace 数据卷，不是缓存**——删卷=毁观测+丢历史，**绝不能 `docker volume rm`**。靠清 build cache / 未用镜像 / 容器日志 truncate / `/root` 下 stale 旧备份就够腾空间。

**诊断口径**：`df -h /`（看是不是 100%）→ `docker system df`（看 Build Cache / Images / Local Volumes 各占多少，Build Cache 大就是它）→ `docker compose logs deeptutor | tail`（确认是 tempdir 崩非代码崩）。

**防爆（预防，避免再"老爆"）**：
- **部署后自动清 build cache**：在 `redeploy_aliyun_fast.sh` 末尾加 `ssh "${REMOTE_HOST}" "docker builder prune -f"`（或给 BuildKit 配 cache GC 上限），让每次 build 的缓存不累积。**这是治本——根因就是 build cache 无人清。**
- **部署前磁盘预检**：发布脚本开头加 `free=$(ssh Aliyun-ECS-2 "df --output=avail -BG / | tail -1")`，`< 10G` 则警告/拒绝，提示先 `docker builder prune -af`。
- **定期维护**：每隔几次部署或每周 `docker builder prune -af && docker image prune -af`（安全，只清未用）。
- **Langfuse 数据增长**：12.5GB 且涨，需配 Langfuse **数据保留(retention)策略**按期清旧 trace（在 Langfuse 内做，不是删卷）；live eval 跑多了 trace 增长更快。
- **认清"快速发布"会 build**：`server_fast_reload_aliyun.sh` 实际 rebuild 镜像，纯 Python/prompt 改动理想应是"复用现有镜像 + 仅 restart"(no-build)；在改成真 no-build 之前，每次发布都要为 build cache 预留空间。
