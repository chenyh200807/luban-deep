# Long Dialog V1 Retest

**时间**: 2026-04-23 10:06:31
**响应模式**: smart
**执行方式**: live_ws
**API Base URL**: `http://127.0.0.1:8001`
**数据源**: `/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/artifacts/long_dialog_round7_full_detail_20260328.json`
**场景数**: 10
**总轮次**: 10

## 总览

- 系统语义理解均分: 88.0/100
- 付费学员满意度均分: 80.0/100
- 平均 TTFT: 0.0ms
- P50 TTFT: 0.0ms
- P90 TTFT: 0.0ms
- 平均延迟: 0.0ms
- P50 延迟: 0.0ms
- P90 延迟: 0.0ms
- 硬错误/空回复: 10
- 跟题/批改断裂: 0
- 出题契约失配: 0
- 显式锚点遗漏: 0
- 上下文重置: 0
- 对比表缺失: 0
- 疑似重复回放: 0
- 慢响应(>45s): 0

## 分场景

| Case | 语义分 | 满意度分 | 硬错误 | 跟题断裂 | 契约失配 | 锚点遗漏 | 上下文重置 | 对比表缺失 | 慢响应 | 平均 TTFT | 平均延迟 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LD_001 | 88 | 80 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0ms | 0.0ms |
| LD_002 | 88 | 80 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0ms | 0.0ms |
| LD_003 | 88 | 80 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0ms | 0.0ms |
| LD_004 | 88 | 80 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0ms | 0.0ms |
| LD_005 | 88 | 80 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0ms | 0.0ms |
| LD_006 | 88 | 80 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0ms | 0.0ms |
| LD_007 | 88 | 80 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0ms | 0.0ms |
| LD_008 | 88 | 80 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0ms | 0.0ms |
| LD_009 | 88 | 80 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0ms | 0.0ms |
| LD_010 | 88 | 80 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0ms | 0.0ms |

## 主要问题轮次

### LD_001 新手理解型：流水施工+横道图+网络计划

- Case 中止: `ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)`

- T1: exception:ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)
  Query: 我刚开始学建筑实务，流水施工一直搞不懂。你先别讲太专业，像给小白讲一样告诉我，什么叫流水施工？
  Response: 

### LD_002 刷题纠错型：双代号网络计划+总时差自由时差

- Case 中止: `ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)`

- T1: exception:ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)
  Query: 我现在学到网络计划了，但我特别容易把总时差和自由时差搞混。你先别长篇讲概念，先给我出3道很短的小题，我做完你再分析。
  Response: 

### LD_003 案例题条件保持型：招投标与合同管理

- Case 中止: `ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)`

- T1: exception:ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)
  Query: 你给我出一道建筑实务案例题，主题是招投标+合同管理，题干不要太长，但要有建设单位、总承包单位、分包单位、监理单位这几个角色。
  Response: 

### LD_004 学习规划型：30天冲刺计划

- Case 中止: `ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)`

- T1: exception:ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)
  Query: 我离一建建筑实务考试还有30天。我平时工作忙，周一到周五每天最多学1.5小时，周末每天4小时。我现在选择题一般，案例题偏弱，尤其是进度管理和索赔。你先帮我做一个30天学习框架，但不要排得太满。
  Response: 

### LD_005 抗干扰型：模板脚手架与安全文明施工

- Case 中止: `ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)`

- T1: exception:ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)
  Query: 我学建筑实务时，模板工程、脚手架、安全文明施工老是混在一起。你先别讲课，先给我出5个判断题，我做完你再说。注意：我最容易混的是安全管理条文。
  Response: 

### LD_006 错题追踪型：钢筋工程

- Case 中止: `ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)`

- T1: exception:ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)
  Query: 我钢筋工程这块总是搞混搭接长度和锚固长度。你先出3道判断题测测我。
  Response: 

### LD_007 换表达型：地下防水工程

- Case 中止: `ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)`

- T1: exception:ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)
  Query: 地下室防水工程中，防水等级是怎么划分的？
  Response: 

### LD_008 情绪干扰型：进度管理

- Case 中止: `ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)`

- T1: exception:ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)
  Query: 我学进度管理快崩溃了，每次算关键线路都算不对，考试还有20天我觉得来不及了。
  Response: 

### LD_009 条件修改型：基坑工程

- Case 中止: `ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)`

- T1: exception:ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)
  Query: 你给我出一道基坑工程安全方案的案例题。要求：基坑深度8m，周边30m内有地铁隧道，采用钢板桩支护。设4个问题。
  Response: 

### LD_010 跨话题型：质量验收 vs 安全管理

- Case 中止: `ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)`

- T1: exception:ConnectionRefusedError: [Errno 61] Connect call failed ('127.0.0.1', 8001)
  Query: 我想先学质量验收，再学安全管理，最后你帮我对比。先从质量验收开始：主体结构验收的基本程序是什么？
  Response: 
