# DeepTutor 运行态备份与恢复 Runbook

这份 runbook 只覆盖一件事：把 `data/user` 作为最小运行态单元做备份和恢复，不引入额外平台依赖。

## 备份对象

默认备份整个 `data/user`，包括：

- `data/user/chat_history.db`
- `data/user/settings/`
- `data/user/workspace/`
- `data/user/tutor_state/`
- `data/user/logs/`

这是当前 runtime 的主边界；脚本会直接复用 `PathService` 的 `data/user` 语义。

## 仓库内脚本

- 备份脚本：[scripts/backup_data.py](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/backup_data.py)
- 恢复脚本：[scripts/restore_data.py](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/restore_data.py)

## 备份命令

在仓库根目录执行：

```bash
python scripts/backup_data.py
```

默认行为：

- 读取当前项目根目录下的 `data/user`
- 生成 `data/backups/deeptutor-data-user-YYYYmmdd-HHMMSSZ.tar.gz`
- 不修改业务目录

如果要指定项目根目录：

```bash
python scripts/backup_data.py --project-root /root/deeptutor
```

如果要把备份放到别的目录：

```bash
python scripts/backup_data.py --backup-dir /mnt/backup/deeptutor
```

## 恢复命令

优先从最近一次备份恢复：

```bash
python scripts/restore_data.py
```

如果要恢复指定归档：

```bash
python scripts/restore_data.py --archive data/backups/deeptutor-data-user-YYYYmmdd-HHMMSSZ.tar.gz
```

如果目标 `data/user` 已经存在且你确认要覆盖：

```bash
python scripts/restore_data.py --archive data/backups/deeptutor-data-user-YYYYmmdd-HHMMSSZ.tar.gz --replace
```

## 校验步骤

备份后先确认两件事：

```bash
tar -tzf data/backups/deeptutor-data-user-YYYYmmdd-HHMMSSZ.tar.gz | head
python scripts/restore_data.py --archive data/backups/deeptutor-data-user-YYYYmmdd-HHMMSSZ.tar.gz --project-root /tmp/deeptutor-drill --replace
```

推荐检查点：

- 压缩包里应看到 `data/user/...`
- 恢复后应存在 `data/user/chat_history.db`
- 恢复后应存在 `data/user/settings/` 和 `data/user/workspace/`

## 演练步骤

建议每次发版前在测试机或临时目录做一次恢复演练。

1. 准备一个干净的演练目录。
2. 先执行备份脚本，生成一份新归档。
3. 在演练目录里恢复这份归档。
4. 检查 `chat_history.db`、`settings/`、`workspace/` 是否都恢复成功。
5. 再启动一次最小服务验证，确认程序能正常读取恢复后的 runtime 数据。

最小演练命令示例：

```bash
python scripts/backup_data.py --project-root /tmp/deeptutor-drill
python scripts/restore_data.py --project-root /tmp/deeptutor-drill --replace
```

## 保留策略建议

最小可执行建议如下：

- 每天保留 1 份最近备份
- 每周保留 1 份周备份
- 每月保留 1 份月备份
- 至少保留最近 7 天的备份

如果磁盘紧张，优先保留：

- 最近 3 份日备份
- 最近 2 份周备份
- 最近 1 份月备份

不要把备份文件放回 `data/user`，否则恢复和备份边界会混在一起。

## 失败处理

如果恢复失败：

- 不要直接重复覆盖生产目录
- 先保留失败现场的归档和报错输出
- 检查归档是否完整、路径是否仍然是 `data/user/...`
- 确认目标目录不是被别的进程占用

## 结论

这套闭环的目标不是做复杂备份平台，而是保证：

- 备份对象明确
- 恢复路径明确
- 校验步骤明确
- 演练步骤明确

这已经足够支撑当前 DeepTutor 的最小运维恢复闭环。
