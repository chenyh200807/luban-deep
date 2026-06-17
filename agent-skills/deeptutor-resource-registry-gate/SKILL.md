---
name: deeptutor-resource-registry-gate
description: "Protects DeepTutor register-before-use resource governance. Use when adding, changing, deleting, or consuming DB connections, table writes, env vars, feature flags, credentials, LLM providers, provider base URLs, long-running processes, cron jobs, route mounts, model defaults, harness authorities, security router/RLS gates, migrations, or governance scanner wiring."
---

# DeepTutor Resource Registry Gate

Use this skill when a change touches foundational resources that can silently
become a second authority if they are not registered before use.

## Authority Chain

- Meta-registry: `contracts/registries.yaml`
- DB resource authority: `contracts/db_registry.yaml`
- Env/flag/credential authority: `contracts/env_registry.yaml`
- Provider/base URL authority: `contracts/provider_registry.yaml`
- Long-running process/cron authority: `contracts/process_registry.yaml`
- Routes: `contracts/index.yaml` `websocket_routes` and `http_routes`
- CI wiring authority for the gates themselves: `scripts/check_registries_meta.py`

These registries are policy filters, not runtime transports. Adding an entry
does not grant permission to write, connect, call, deploy, or flip a default; it
only makes an existing or proposed resource machine-checkable.

## Start Frame

```text
resource fact:
resource class:
current registry:
writer/caller/owner:
runtime authority:
guard script:
CI wiring:
grandfathered or new:
verification command:
```

If the `current registry` is unknown, inspect `contracts/registries.yaml` before
editing code.

## Register-Before-Use Rules

- Raw Postgres connection or direct SQL write: register in
  `contracts/db_registry.yaml` and use the connection-factory path when
  possible.
- Env var, feature flag, or credential read: register in
  `contracts/env_registry.yaml`. Feature flags must record default and rollout
  semantics; typo-to-default is a false-green risk.
- LLM/embedding provider or provider base URL: register in
  `contracts/provider_registry.yaml`; new providers must not be added to
  deprecated provider copies.
- Persistent `asyncio.create_task`, daemon, cron, or long-lived process: register
  in `contracts/process_registry.yaml`, including owner and stop mechanism.
- REST/WS route existence: register in `contracts/index.yaml`; chat WS remains
  exactly `/api/v1/ws`.
- New governance scanner: register in `contracts/registries.yaml` and ensure
  every `pr_gate` scanner appears in `.github/workflows/tests.yml`.

## Red Flags

- A new env flag is read directly without a registry entry.
- A new raw DB URL env or table write appears outside the DB registry.
- A provider endpoint is hardcoded at a call site.
- A daemon or cron job has no owner, lifecycle, or stop path.
- A scanner exists on disk but is not cataloged or wired into CI.
- A registry entry is treated as runtime authorization rather than a policy
  declaration.

## Verification

Run the narrowest relevant guard and preserve the exact command:

```bash
python scripts/check_registries_meta.py
python scripts/check_db_registry.py --all
python scripts/check_env_registry.py --all
python scripts/check_provider_registry.py --all
python scripts/check_process_registry.py --all
python scripts/ci/check_rest_route_allowlist.py
python scripts/ci/check_websocket_route_allowlist.py
```

For normal changed-file validation, also run:

```bash
python scripts/check_contract_guard.py <changed files>
```

Before closing:

- [ ] The resource class maps to one canonical registry.
- [ ] Any new resource is registered before use.
- [ ] The relevant guard command passed or the blocker is named.
- [ ] The change did not create a second inventory or runtime authority.
