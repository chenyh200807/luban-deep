# Graph prompt snapshot

系统消息、topic definitions、source pack、case、response schema 与 baseline 完全相同。

唯一额外 block 是：

```json
{
  "prerequisite_projection": [
    {"prerequisite_topic_id":"np01","target_topic_id":"np02","strength":"hard"},
    {"prerequisite_topic_id":"np02","target_topic_id":"np03","strength":"hard"},
    {"prerequisite_topic_id":"np05","target_topic_id":"np07","strength":"hard"},
    {"prerequisite_topic_id":"np06","target_topic_id":"np08","strength":"hard"},
    {"prerequisite_topic_id":"np03","target_topic_id":"np04","strength":"soft"},
    {"prerequisite_topic_id":"np05","target_topic_id":"np06","strength":"soft"}
  ]
}
```

该 block 只允许影响 teaching/remediation context，不得改变 answer key、required terms、official score 或 LearnerState。
