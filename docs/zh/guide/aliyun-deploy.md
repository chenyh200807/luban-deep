# 阿里云 ECS 部署（8.135.42.145）

这份说明对应当前主服务器 `8.135.42.145`，部署目录固定为 `/root/deeptutor`。

## 当前服务器结论

- 当前可用服务器：`Aliyun-ECS-2` -> `8.135.42.145`
- 现网项目目录：`/root/luban`
- 不要把 `deeptutor` 上传到 `/root/luban`
- 当前可直接使用的 DeepTutor 端口：
  - 前端 `3782`
  - 后端 `8001`
- 宿主机 `80/443` 已由现有 nginx 占用，因此第一阶段建议先直接用端口访问

## 仓库内新增的部署入口

- 上传脚本：[scripts/sync_to_aliyun.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/sync_to_aliyun.sh)
- 快速重启脚本：[scripts/restart_aliyun.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/restart_aliyun.sh)
- 后端快速发布脚本：[scripts/redeploy_aliyun_fast.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/redeploy_aliyun_fast.sh)
- 一键部署脚本：[scripts/deploy_aliyun.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/deploy_aliyun.sh)
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
- `SERVICE_ENV=production`
- `APP_ENV=production`
- `MEMBER_CONSOLE_USE_REAL_SMS=true`

你需要补齐至少这些项：

- `LLM_API_KEY`
- `EMBEDDING_API_KEY`
- `WECHAT_MP_APP_ID`
- `WECHAT_MP_APP_SECRET`
- `ALIYUN_SMS_ACCESS_KEY_ID`
- `ALIYUN_SMS_ACCESS_KEY_SECRET`
- `ALIYUN_SMS_SIGN_NAME`
- `ALIYUN_SMS_TEMPLATE_CODE`

如果你继续使用 DashScope，这两个 key 可以相同。

如果不显式把 `SERVICE_ENV` / `APP_ENV` 设成 `production`，或者没把
`MEMBER_CONSOLE_USE_REAL_SMS` 打开，小程序验证码会退回调试模式，接口返回
`debug_code`，不会真正发短信。

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
- 会排除 `.env`、`data/`、`.git`、`.venv`、`node_modules`
- 这样不会覆盖服务器上已经生成的数据和密钥

如果你想开发时持续同步：

```bash
bash scripts/sync_to_aliyun.sh watch
```

### 3. 启动部署

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
bash scripts/deploy_aliyun.sh
```

脚本会做这些事：

1. 同步仓库到 `Aliyun-ECS-2:/root/deeptutor`
2. 远程执行 `scripts/server_bootstrap_aliyun.sh`
3. 若 `.env` 缺失则自动生成模板
4. 若 `.env` 已存在则执行 `docker compose up -d --build`

这条是“完整部署”路径，适用于：

- 第一次上线
- 修改了 `Dockerfile`
- 修改了 `requirements*.txt`
- 修改了前端构建产物或 Node 依赖
- 需要重新安装系统依赖

### 4. 访问地址

- 前端：<http://8.135.42.145:3782>
- 后端：<http://8.135.42.145:8001>
- API 文档：<http://8.135.42.145:8001/docs>

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
bash scripts/redeploy_aliyun_fast.sh

# 完整重建发布
bash scripts/deploy_aliyun.sh
```

三条路径的区别：

- `restart_aliyun.sh`
  - 只做 `docker compose restart deeptutor`
  - 不同步代码，不重建镜像
  - 适合临时恢复服务
- `redeploy_aliyun_fast.sh`
  - 先 `rsync` 到服务器
  - 再把 `deeptutor/` 等后端代码 `docker cp` 到正在运行的容器
  - 最后重启容器
  - 适合 Python 后端、Prompt、YAML、路由等无需重装依赖的改动
- `deploy_aliyun.sh`
  - 先同步，再执行 `docker compose up -d --build`
  - 最慢，但最完整
  - 适合依赖、Dockerfile、前端构建相关改动

## 当前部署建议

第一阶段先用端口访问，不先接管现有 `80/443`：

- 风险最低
- 不影响 `/root/luban`
- 最容易验证 DeepTutor 是否稳定

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

现在仓库已经补了阿里云默认镜像源和缓存挂载，但完整部署仍然会比“快速发布”慢很多。
