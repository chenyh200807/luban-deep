# Proposed Remote Env Diff (not applied)

Target file after explicit M19F authorization only:

`Aliyun-ECS-2:/root/deeptutor/.env`

## Add or set

```dotenv
LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=true
LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_COHORT=qa_,operator_
```

## Kill switch / rollback settings

```dotenv
LUBAN_V1_LLM_ADJUDICATOR_ENABLED=false
LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=false
```

## Explicit exclusions

- Do not enable any broad production default.
- Do not enable canonical learner truth write.
- Do not enable production DB write.
- Do not include `test_` in the default cohort; `test_` remains explicit regression only.
- Do not absorb M20.1 delta into the current M19C/M19D runtime.
- Do not write any remote path outside `/root/deeptutor`.

This round does not modify Aliyun `.env`.
