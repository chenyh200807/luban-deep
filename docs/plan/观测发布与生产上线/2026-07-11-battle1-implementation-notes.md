# Battle 1 实施偏离账本（append-only，新条目在顶）

> 规则：实施中遇到 edge case 一律选保守方案并在此记录偏离；每条含【任务/偏离/原因/影响面/验证】。fix-test 日志（含失败尝试）同记于此。

## 2026-07-11 W2-T1 PRAGMA synchronous（批1a）
- **偏离**：设计前提"运行时新连接回落 synchronous=FULL"在本机被证伪——macOS SQLite 3.51 编译带 `SQLITE_DEFAULT_WAL_SYNCHRONOUS=1`，WAL 库上新连接默认已是 NORMAL(1)（实测：fresh conn=2，WAL 后新 conn=1）。
- **裁决**：修复保留但语义从"性能修复"降为"跨环境确定性钉扎"——生产容器（Debian python 镜像）编译默认未验证，显式 PRAGMA 消除环境彩票；测试断言 WAL+NORMAL 不变量（本机非 RED，属不变量文档化）。
- **影响面**：`sqlite_store.py:_connect` +7 行注释+1 行 PRAGMA；生产收益待部署后在容器内 `PRAGMA synchronous` 取证（若容器默认已 NORMAL 则本刀零收益零风险）。
- **验证**：tests/services/session/test_sqlite_store.py 40 passed。

## 2026-07-11 执行方式偏离（全局）
- Fable/Opus subagent 均撞账号 session limit（21:20 SGT 重置）→ 批 1 起改为主控内联逐刀执行+每刀窄提交；设计与指挥官裁决仍为唯一施工蓝图。
