# 鲁班编译源语料备份 manifest(bus factor=1 缓解)

> 背景:六专家审计 MUST——编译线源语料(教材/讲义/真题挖矿产物)只存单机无 git,bus factor=1。
> 本 manifest 把"备份存在性+完整性指纹"入 git;语料本体不进 git(403MB 二进制)。

## 备份记录

| 日期 | 源 | 归档 | SHA256 | 大小 | 远端位置 | 远端核验 |
|---|---|---|---|---|---|---|
| 2026-07-12 | `~/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026`(2077 文件) | `luban_corpus_20260711.tar.gz` | `f1daaf2270d319886e3c1f7e55356f272f578783c28bd3f259ae97a1418b17f1` | 403MB | `Aliyun-ECS-2:/root/deeptutor/backups/luban_corpus_20260711.tar.gz` | sha256sum 远端实测=本地,逐字一致 |

## 恢复方法

```bash
scp Aliyun-ECS-2:/root/deeptutor/backups/luban_corpus_20260711.tar.gz .
shasum -a 256 luban_corpus_20260711.tar.gz  # 必须等于上表 SHA256
tar -xzf luban_corpus_20260711.tar.gz  # 解出 2026/ 目录
```

## 纪律

- 语料有实质增量(新教材版/新批次挖矿)后应重新打包追加一行,旧归档保留(阿里云盘余量 26G,单份 403MB 可存多代)。
- 本 manifest 是"备份是否存在、是否完整"的唯一 git 内权威;恢复前必核 SHA256。
- 阿里云写边界:备份只落 `/root/deeptutor/` 下(AGENTS §3.7)。
