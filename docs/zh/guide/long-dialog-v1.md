# Long Dialog V1 复测说明

这份文档记录当前仓库里 `long dialog V1` 的**启动方式、数据来源、运行命令、输出位置和注意事项**。

目标不是还原旧 FastAPI 项目的全部评测基础设施，而是让你以后在 DeepTutor 仓库里可以**稳定地再次发起同口径复测**。

## 1. 这套复测现在是怎么启动的

当前仓库里已经没有旧系统原始的：

```text
eval/sets/long_dialog_v1.jsonl
```

所以现在的做法是：

1. 从旧系统留存的长对话 artifact 中读取 `session_full_conversations`
2. 抽出每条链真实的 `user_query`
3. 用当前 DeepTutor 的 `TurnRuntimeManager` 逐轮重放
4. 全部走 `construction_exam_tutor + smart`
5. 在本仓库 `tmp/` 下输出 JSON 和 Markdown 报告

脚本已经固化为：

[`scripts/run_long_dialog_v1_retest.py`](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/run_long_dialog_v1_retest.py)

## 2. 默认数据源

脚本默认优先读取下面这个历史明细：

```text
/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222_broken_backup_20260414_002321/artifacts/long_dialog_round7_full_detail_20260328.json
```

这里面保留了 10 条长对话链的完整 `session_full_conversations`。

如果这个路径以后变了，就用 `--source-json` 手工指定。

## 3. 运行前检查

### 3.1 Python 版本

必须用 **Python 3.11+**。本机自带的 `python3` 目前是 `3.9.6`，不能直接跑。

先确认：

```bash
python3 --version
python3.11 --version
```

当前推荐直接用：

```bash
python3.11
```

### 3.2 LLM 配置

先确认当前模型配置可用：

```bash
python3.11 - <<'PY'
from deeptutor.services.llm.config import get_llm_config
cfg = get_llm_config()
print("binding=", cfg.binding)
print("model=", cfg.model)
print("base_url=", cfg.base_url)
print("effective_url=", cfg.effective_url)
print("has_api_key=", bool(cfg.api_key))
PY
```

如果这里拿不到模型、URL 或 API key，不要启动复测。

## 4. 常用启动命令

### 4.1 跑单条链做冒烟

```bash
python3.11 scripts/run_long_dialog_v1_retest.py --cases LD_001
```

### 4.2 跑两三条链做回归

```bash
python3.11 scripts/run_long_dialog_v1_retest.py --cases LD_001,LD_002,LD_003
```

### 4.3 跑代表性关键轮次

这个模式不会跑整条链，只跑一些最能暴露问题的关键轮次：

```bash
python3.11 scripts/run_long_dialog_v1_retest.py --turn-mode focus
```

目前 `focus` 主要覆盖：

- `LD_003`：案例题条件保持
- `LD_009`：条件修改推理
- `LD_010`：跨话题切换再回收

### 4.4 跑全部 case

```bash
python3.11 scripts/run_long_dialog_v1_retest.py
```

如果只想跑前几个 case：

```bash
python3.11 scripts/run_long_dialog_v1_retest.py --max-cases 3
```

### 4.5 手工指定历史数据源

```bash
python3.11 scripts/run_long_dialog_v1_retest.py \
  --source-json /absolute/path/to/long_dialog_round7_full_detail_20260328.json
```

## 5. 输出在哪里

默认输出到：

```text
tmp/
```

每次运行会生成两份文件：

- `long_dialog_v1_retest_smart_<timestamp>.json`
- `long_dialog_v1_retest_smart_<timestamp>.md`

如果你改了 `--teaching-mode`，文件名里的 `smart` 会变成对应模式名。

## 6. 当前评审口径

脚本现在会重点统计这些问题：

- 硬错误/空回复
- 跟题/批改断裂
- 出题数量契约失配
- 显式锚点遗漏
- 上下文重置
- 对比表缺失
- 疑似重复回放
- 慢响应（>45s）

同时给两个分数：

- 系统语义理解能力
- 付费学员满意度

## 7. 为什么这次不再直接用旧项目脚本

旧项目的原始脚本是：

```text
FastAPI20251222/scripts/run_long_dialog_eval.py
```

但它依赖的原始 eval set 在当前机器上已经不完整，而且旧项目目录本身也发生过备份/恢复。

所以现在 DeepTutor 侧的复测以**历史 artifact 还原用户轮次**为准，而不是继续依赖旧目录下的原生启动链路。

## 8. 已知限制

### 8.1 full 模式很慢

当前 smart 模式单轮真实延迟可能落在：

- 45s
- 60s
- 90s
- 甚至 140s

所以整套 110 轮 full run 很可能超过 2 小时。

### 8.2 单轮超时后，当前 case 直接中止

脚本现在的处理策略是：

- 如果某一轮超过 `--per-turn-timeout`
- 直接记录异常
- 中止当前 case 后续轮次

这是故意设计的，目的是避免后续再触发：

```text
Session already has an active turn
```

这种连锁污染。

### 8.3 现在的 source 是“历史真实对话明细”，不是原始题集 JSONL

所以它更接近“真实线上回放复测”，而不是“原始基准集纯净重跑”。

## 9. 推荐使用顺序

以后要复测时，建议按这个顺序来：

1. 先确认 `python3.11` 和 LLM 配置
2. 先跑 `LD_001`
3. 再跑 `LD_001,LD_002,LD_003`
4. 如果要看复杂语义能力，再跑 `--turn-mode focus`
5. 只有在确认延迟和超时可接受后，再决定是否跑 full

## 10. 这次文档沉淀的对应文件

- 脚本：
  [`scripts/run_long_dialog_v1_retest.py`](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/run_long_dialog_v1_retest.py)
- 说明：
  [`docs/zh/guide/long-dialog-v1.md`](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/zh/guide/long-dialog-v1.md)

以后如果启动方式变了，就优先更新这两个文件，不要只留在聊天记录里。
