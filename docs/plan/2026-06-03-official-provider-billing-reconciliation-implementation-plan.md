# Official Provider Billing Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a provider-neutral official billing reconciliation mechanism so DeepTutor can prove whether Langfuse/BI token and cost statistics match the actual charges from DeepSeek official API and Alibaba DashScope/Bailian.

**Architecture:** Treat `UsageLedger` as the internal per-call charge attribution authority, with provider-specific official adapters for DeepSeek and Bailian. Reconciliation compares three ledgers separately per provider and billing scope: runtime internal ledger, provider official usage/balance/billing data, and BI cost rollups.

**Tech Stack:** Python, FastAPI, SQLite `llm_usage.db`, Langfuse observability adapter, Alibaba Cloud BssOpenApi, DeepSeek `/user/balance`, DeepSeek console usage export CSV/ZIP, pytest.

---

## Status

`Proposed v0.4` on 2026-06-03.

This is an implementation plan only. It does not change production billing, does not deploy to Aliyun, and does not call paid LLM APIs during tests.

## Source Authority

Official provider docs checked on 2026-06-03:

- DeepSeek pricing: <https://api-docs.deepseek.com/quick_start/pricing>. Current pricing is per 1M tokens and distinguishes cache-hit input, cache-miss input, and output. The page also says prices may change, so local pricing must carry `pricing_source_checked_at`.
- DeepSeek model naming: the same pricing page says `deepseek-chat` and `deepseek-reasoner` map to `deepseek-v4-flash` modes and are scheduled for deprecation on 2026-07-24 15:59 UTC. Reconciliation must preserve both raw model and normalized pricing model.
- DeepSeek context caching usage fields: <https://api-docs.deepseek.com/guides/kv_cache>. The API response usage object exposes `prompt_cache_hit_tokens` and `prompt_cache_miss_tokens`.
- DeepSeek balance API: <https://api-docs.deepseek.com/api/get-user-balance/>. It returns availability plus CNY/USD balances; it is not a billing-cycle amount source.
- DeepSeek official FAQ: Usage page supports monthly export by API key; the exported package contains two CSV files, and the amount file contains usage details broken down by key. The FAQ does not guarantee stable column names, so parser work must start with a real export schema audit.
- Alibaba Cloud `DescribeInstanceBill`: <https://www.alibabacloud.com/help/en/boa/latest/api-bssopenapi-2017-12-14-describeinstancebill>. It supports billing-cycle querying and returns provider-native currency values; current-month bills can still be incomplete before settlement.

## Current Baseline

Current default runtime is DeepSeek official:

- `.env.example`: `LLM_BINDING=deepseek`, `LLM_MODEL=deepseek-v4-flash`, `LLM_HOST=https://api.deepseek.com/v1`
- `deeptutor/config/defaults.py`: `DEFAULT_LLM_PROVIDER = "deepseek"`

Current runtime can still charge Alibaba:

- `deeptutor/services/provider_registry.py` registers both `deepseek` and `dashscope`.
- `deeptutor/services/config/provider_runtime.py` supports `LLM_FALLBACK_MODEL` and `LLM_FALLBACK_BINDING`.
- `deeptutor/tutorbot/providers/deeptutor_adapter.py` can construct the fallback provider from resolved runtime config.

Existing cost authority is incomplete:

- `deeptutor/services/observability/usage_ledger.py` stores provider/model/tokens/cost and metadata, but does not expose DeepSeek cache hit/miss rollups.
- `deeptutor/tutorbot/providers/openai_compat_provider.py::_extract_usage` currently drops provider-specific fields such as `prompt_cache_hit_tokens` and `prompt_cache_miss_tokens`.
- `deeptutor/services/observability/langfuse_adapter.py::estimate_model_cost` prices only simple input/output/total, so DeepSeek cache-hit pricing cannot be reconciled accurately.
- `deeptutor/services/bi_service.py::get_cost_reconciliation` already queries Bailian telemetry/billing, but `system_global_bailian` is hard-coded to provider `dashscope` and the endpoint is not provider-neutral.

Current package-margin requirement adds one more constraint:

- A user-facing "1 conversation" is not always one provider API call. A single billable turn can include retries, fallback provider calls, tool-planning calls, summary calls, or admin/eval traffic. The reconciliation plan must be able to roll up provider cost per billable user turn, otherwise it cannot safely support the 198/698 次卡毛利 decisions.

## One Business Fact

For every LLM call, the system must know:

> Which provider account actually charged money, for which model, under which token categories, and what official data proves or disputes that charge.

## Single Authority

Internal authority:

- `UsageLedger` is the canonical internal ledger for per-call provider attribution.
- Langfuse traces are observability evidence, not the billing authority.
- BI `cost_summary` is a read-model rollup, not the billing authority.

Official authority:

- DeepSeek official per-call token truth is the provider `usage` object returned by the API.
- DeepSeek official monthly monetary truth is the console Usage export CSV/ZIP amount file by API key. `/user/balance` is only an account availability snapshot and must not be used as账期金额 delta authority.
- Alibaba official truth is BssOpenApi `DescribeInstanceBill`, scoped by product code/product type/workspace/API key/model when available.

## Non-Goals

- Do not create a second wallet/points authority.
- Do not change package pricing or user point deduction.
- Do not merge DeepSeek USD/CNY and Bailian CNY into one fake currency. Keep provider-native currency in reconciliation; only add converted display values if a separately configured FX source exists.
- Do not invent a DeepSeek bill-detail API. If no official API exists for detailed monthly usage, use the official console export path.
- Do not add a new BI top-level tab in P0. Extend existing cost/reconciliation surfaces first.

## Currency Contract

Every reconciliation payload must keep these currency concepts separate:

- `pricing_currency`: the currency used by the local pricing table that estimated a call.
- `official_currency`: the currency found in the official provider export or bill.
- `account_currency`: the currency returned by an account balance endpoint when available.

Rules:

- Amount deltas are calculated only when internal and official amounts have the same currency.
- Cross-currency values can be displayed side by side, but the reconciliation status must include `currency_mismatch` and avoid a numeric amount delta.
- DeepSeek `/user/balance` can populate `account_currency`, but it cannot populate `official_currency` for a billing cycle.
- Local pricing constants must include `pricing_source_checked_at` so stale price tables are visible.

## Cost Confidence Contract

BI must not collapse all cost data into one "total cost" number. Every response should expose:

- `official_cost`: provider official bill/export amount for the provider and billing scope.
- `local_measured_cost`: provider-returned usage priced locally by model/token category.
- `estimated_cost`: local tokenizer or fallback estimate when provider usage is missing.
- `unattributed_cost`: official amount that cannot be explained by internal calls, or internal calls that cannot be linked to an official scope.

Default trust thresholds:

- `<= 2%` amount delta in the same currency: `trusted`.
- `> 2% and <= 5%`: `warning`.
- `> 5%`: `untrusted`, requiring operator review before using the BI cost number for package margin decisions.

## Cost Basis Contract

The same official bill supports different business questions. The API response must name the cost basis being used:

- `list_price_cost`: sustainable unit-cost view, using provider list or pretax pricing and measured cache fields. This is the default basis for package pricing and gross-margin decisions.
- `net_charge_cost`: official net charge after provider discounts or bill adjustments. This is the default basis for finance cash reconciliation.
- `cash_paid_cost`: cash actually paid after granted balance, coupons, or credits. This is useful for treasury but must not be used alone to prove product margin.
- `credit_consumed`: granted balance, coupons, or credits consumed when the provider exposes them.

Rules:

- Package margin dashboards must use `list_price_cost` unless an operator explicitly switches basis.
- DeepSeek granted balance and Alibaba discounts can improve short-term cash burn, but they must not make the 198/698 package look sustainably profitable.
- If an official source exposes only net amount and not list/pretax amount, mark `list_price_cost.status = "estimated_from_local_pricing"` and keep `net_charge_cost` separate.

## Billing Scope Contract

Every reconciliation query must be scoped tightly enough to answer "which usage belongs to this business decision":

```text
billing_scope_id =
  provider_name
  + charged_account_fingerprint
  + runtime_environment
  + cost_center
  + billing_cycle
  + raw_model/pricing_model
```

Internal ledger metadata must include:

- `charged_provider_name`: provider that actually charged money.
- `requested_provider_name`: provider originally requested before fallback.
- `api_key_fingerprint`: stable SHA-256 fingerprint prefix or provider key id; never the raw key.
- `provider_account_id`: explicit account/workspace/key id when the provider exposes one.
- `runtime_environment`: `production`, `staging`, `local`, `test`, or `unknown`.
- `cost_center`: `prod_user_chat`, `bi_admin`, `eval`, `benchmark`, `cron`, `local_dev`, or `unknown`.
- `billable_unit`: `conversation_turn`, `background_task`, `eval_case`, or `non_billable`.
- `billable_turn_id`: turn id that caused one user-visible deduction when available.
- `raw_model`, `normalized_model`, `pricing_model`: preserve official/raw model identity while still pricing aliases consistently.

Rules:

- `unknown` scope values are allowed for compatibility, but they make the result `warning` and cannot be used as trusted package-margin evidence.
- Fallback calls must keep both `requested_provider_name` and `charged_provider_name`; provider drift is a warning even if the user response succeeded.
- Evaluation, benchmark, BI admin, local dev, and cron costs must be visible but excluded from product package margin by default.

## Billable Conversation Contract

For 次卡/套餐 decisions, the unit is a billable user conversation turn, not a provider call.

BI margin output must expose:

- `billable_turns`: number of user turns that deducted or would deduct a conversation credit.
- `provider_calls`: number of LLM provider calls under those turns.
- `calls_per_billable_turn`: `provider_calls / billable_turns`.
- `list_price_cost_per_billable_turn`: sustainable provider cost per billable turn.
- `unattributed_provider_calls`: provider calls without `billable_turn_id`.
- `non_billable_cost`: eval/admin/cron/local usage excluded from package margin.

Rules:

- If `billable_turns = 0`, do not calculate per-conversation cost.
- If more than 5% of provider cost lacks `billable_turn_id`, package-margin confidence is `untrusted` even if provider totals match.
- Retries and fallback calls should be allocated to the same `billable_turn_id`; otherwise failed retries can disappear from margin math.

## Wallet Capture Authority Contract

`billable_turn_id` must come from the real wallet/points capture result, not from provider metadata alone.

Current code authority:

- `deeptutor/services/session/turn_runtime.py::_capture_mobile_points` is the mini-program post-turn capture point.
- It calls `wallet_service.record_usage_points` with `idempotency_key = "mini_program_capture:{turn_id}"`.
- It returns `status="captured"` only after wallet service accepts the capture.

Rules:

- Provider calls may record provisional `turn_id` and `scope_id` while the LLM is running.
- A usage event becomes package-margin eligible only after wallet capture returns `status="captured"` for the same turn.
- `UsageLedger` may mirror wallet capture metadata for attribution, but wallet capture remains the billable authority.
- If a turn generated provider cost but wallet capture failed, skipped, or had no wallet authority, its cost must be visible as `non_billable_cost` and excluded from package-margin numerator by default.
- The idempotency key and wallet reference id must be carried into ledger metadata as evidence: `billing_capture_status`, `billing_capture_idempotency_key`, `billing_reference_id`, and `billing_amount_points`.

## Reconciliation State Contract

Provider blocks should fail closed with explicit states:

- `trusted`: same-currency amount delta is `<= 2%` and scope coverage is complete.
- `warning`: amount delta is `> 2% and <= 5%`, or scope is partially unknown, or current-month official bill may be incomplete.
- `untrusted`: amount delta is `> 5%`, official data is present but cannot explain internal usage, or billable-turn attribution gap is above 5%.
- `unconfigured`: official connector/export is not configured.
- `waiting_for_official_export`: internal ledger exists but DeepSeek monthly export has not been imported.
- `unsupported_export_schema`: official export columns cannot be mapped safely.
- `currency_mismatch`: internal and official amounts use different currencies, so no amount delta is computed.
- `scope_mismatch`: official export/account scope does not match the internal API key/workspace/environment scope.
- `official_bill_pending`: official source is known to be incomplete for the current period.
- `error`: connector failed unexpectedly.

No state except `trusted` can be used as green evidence for package-margin decisions.

## Official Export Security Contract

Official billing exports may contain API-key-level spend data. Treat them as sensitive operational data:

- Raw official exports must live only under ignored local/runtime directories such as `data/user/official_billing/` or `var/official_billing/`.
- Do not upload raw exports through a public BI endpoint in P0.
- Parser code must reject symlinked export paths unless they resolve under the configured export root.
- ZIP files must be read in-memory for headers/CSV streams; never extract arbitrary archive paths to disk.
- Enforce a conservative maximum file size before parsing.
- Compute and store `source_file_sha256`, `source_file_name`, `billing_cycle`, `provider_name`, `imported_at`, and `schema_hash` in the returned manifest.
- Importing the same file hash for the same provider/cycle must be idempotent.
- Fixtures committed to git must preserve real header names but contain synthetic row values only.

## Sensitive API Access Contract

Official billing reconciliation is more sensitive than ordinary BI read models.

Rules:

- `/api/v1/bi/cost/reconciliation` must require `require_bi_admin` once it can return official provider data.
- `X-Metrics-Token` and `DEEPTUTOR_BI_PUBLIC_ENABLED=true` must not be sufficient for official billing reconciliation.
- Tests must prove admin access succeeds and metrics-token-only access is rejected.
- Raw exports must never be uploaded through this endpoint in P0; imports are filesystem/runtime operations only.

## Current Uncertainties And Validation Plan

These are not blockers for writing P0 code, but they are gates before trusting margin output:

| Uncertainty | Why it matters | Validation | Fallback |
| --- | --- | --- | --- |
| DeepSeek export column names | Parser cannot safely map amount/model/key/currency without real headers | Task 0 header audit from a real export | `unsupported_export_schema` |
| DeepSeek account currency | Pricing page is USD-denominated, balance can be CNY or USD | Compare export currency and `/user/balance` currencies | Side-by-side display with `currency_mismatch` |
| Cache fields in actual streaming path | Local cost is wrong if SDK drops provider-specific usage | Low-cost live trace or mocked SDK object matching response shape | Mark `local_measured_cost` incomplete |
| Provider request id availability | Helps sample official/internal discrepancies | Inspect SDK response headers/object fields | Use Langfuse trace id + turn id only |
| Alibaba current-month settlement lag | Current month may change before final bill | Query previous closed cycle and current cycle separately | `official_bill_pending` for current cycle |
| Multi-key production deployment | Official export by key cannot match internal usage without key scope | Store `api_key_fingerprint` or provider key id | `scope_mismatch` and margin untrusted |

## Use Case Matrix

| Scenario | Question | Required evidence | Fail-closed behavior |
| --- | --- | --- | --- |
| Daily finance check | Are we spending money on the providers we expect? | Internal ledger by provider, balance snapshot, Bailian bill if available | Warn on provider drift and unconfigured official sources |
| Month-end close | Does official provider spend match internal ledger? | DeepSeek Usage export amount file; Alibaba `DescribeInstanceBill`; same billing cycle | Mark unsupported schema, bill pending, or currency mismatch explicitly |
| 198/698 package margin | What is sustainable cost per billable turn? | `prod_user_chat`, `billable_turn_id`, list-price basis, official monthly close | Do not trust if non-billable or unattributed costs exceed threshold |
| Provider fallback incident | Did fallback silently charge Alibaba? | `requested_provider_name` vs `charged_provider_name`; provider ledger totals | Show drift even if user-facing chat succeeded |
| Eval/benchmark run | Are offline tests polluting product margin? | `cost_center=eval|benchmark` and runtime environment | Exclude from package margin, keep visible in ops totals |
| API key rotation | Did old and new keys both spend money? | `api_key_fingerprint` or provider key id in internal and official data | Mark scope mismatch if official key cannot be mapped |
| Export schema drift | Did provider change the CSV format? | Header audit and redacted fixture generated from real export | Return `unsupported_export_schema`; do not guess columns |
| Pricing page changes | Did local cost table become stale? | `pricing_source_checked_at` and official pricing link | Warning if price source is stale before margin use |

## Implementation Slices

P0 should be shipped in cuts that each produce usable evidence:

1. **P0A - Measurement foundation:** Task 0.5, Task 1, Task 1.5, Task 2, Task 3, Task 4. Delivers reliable internal attribution, real wallet-capture binding, and cache-aware local cost without waiting for a DeepSeek export file.
2. **P0B-0 - Official export schema gate:** Task 0. Runs as soon as a real DeepSeek Usage export is available. If unavailable, the product still ships P0A and BI reports `waiting_for_official_export`.
3. **P0B - Official reconciliation:** Task 5, Task 5.5, Task 6, Task 7, Task 8. Delivers DeepSeek export import, import manifest idempotency, Bailian provider-neutral output, and BI API response shape.
4. **P0C - Operating closure:** runbook, alert thresholds, and optional Task 9 UI projection. Delivers a repeatable finance/margin workflow without changing pricing or wallet authority.

## File Structure

Create:

- `deeptutor/services/observability/deepseek_billing.py` - DeepSeek balance client and usage export parser.
- `deeptutor/services/observability/official_billing_imports.py` - provider-neutral official export import manifest store.
- `deeptutor/services/observability/provider_reconciliation.py` - provider-neutral reconciliation data structures and delta helpers.
- `scripts/audit_deepseek_usage_export.py` - deterministic local audit for DeepSeek official export headers and redacted fixtures.
- `tests/services/test_deepseek_billing.py` - DeepSeek balance/export parser tests.
- `tests/services/test_official_billing_imports.py` - import manifest idempotency tests.
- `tests/services/test_provider_reconciliation.py` - provider-neutral scope, cost-basis, and delta tests.
- `tests/tutorbot/providers/test_openai_compat_provider_usage.py` - provider usage and attribution tests.
- `tests/fixtures/deepseek_usage_export/README.md` - documents how redacted export fixtures are produced.

Modify:

- `.gitignore` - keep raw official billing exports out of git.
- `deeptutor/tutorbot/providers/openai_compat_provider.py` - preserve provider-specific usage fields from OpenAI-compatible responses.
- `deeptutor/tutorbot/providers/base.py` - normalize DeepSeek cache hit/miss fields into `usage_details`.
- `deeptutor/services/observability/langfuse_adapter.py` - estimate DeepSeek cache-aware cost and pass native cost metadata to `UsageLedger`.
- `deeptutor/services/observability/usage_ledger.py` - expose provider-native rollups, metadata-derived token categories, billing-scope filters, and billable-turn rollups.
- `deeptutor/services/observability/bailian_billing.py` - keep existing BssOpenApi adapter; only normalize output into provider-neutral shape.
- `deeptutor/services/bi_service.py` - make cost reconciliation provider-aware.
- `deeptutor/api/routers/bi.py` - add `provider` query parameter to `/api/v1/bi/cost/reconciliation`.
- `.env.example` - document optional reconciliation env vars and runtime cost-center defaults.
- `tests/services/test_usage_ledger.py` - cache/currency/metadata rollup coverage.
- `tests/services/test_langfuse_observability.py` - DeepSeek cache-aware cost coverage.
- `tests/api/test_bi_router.py` - provider-aware reconciliation payload coverage.

Review only if P1 UI is requested:

- `web/components/bi/*`
- `web/lib/member-api.ts`

## Task 0: Audit Real DeepSeek Usage Export Schema

**Files:**

- Create: `scripts/audit_deepseek_usage_export.py`
- Create: `docs/qa/2026-06-03-deepseek-usage-export-schema-audit.md`
- Create: `tests/fixtures/deepseek_usage_export/README.md`
- Modify: `.gitignore`

- [ ] **Step 1: Create the local schema audit script**

Create `scripts/audit_deepseek_usage_export.py`:

```python
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import zipfile


def _headers_from_text(handle: io.TextIOBase) -> list[str]:
    reader = csv.reader(handle)
    return [str(value or "").strip() for value in next(reader, [])]


def _iter_csv_headers(path: Path) -> list[dict[str, list[str] | str]]:
    rows: list[dict[str, list[str] | str]] = []
    if path.is_dir():
        for file in sorted(path.glob("*.csv")):
            with file.open("r", encoding="utf-8-sig", newline="") as handle:
                rows.append({"name": file.name, "headers": _headers_from_text(handle)})
        return rows
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if not name.lower().endswith(".csv"):
                    continue
                with archive.open(name) as raw:
                    text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                    rows.append({"name": Path(name).name, "headers": _headers_from_text(text)})
        return rows
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{"name": path.name, "headers": _headers_from_text(handle)}]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("export_path", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = {"files": _iter_csv_headers(args.export_path)}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for item in payload["files"]:
            print(f"{item['name']}: {', '.join(item['headers'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Ignore raw official exports**

Add to `.gitignore`:

```gitignore
# Official billing exports may contain API-key-level cost details.
data/user/official_billing/
var/official_billing/
```

- [ ] **Step 3: Harden export path handling**

Before reading a path, the script must:

- Resolve the input path and reject paths that do not exist.
- Reject symlinked files unless the resolved target is under the configured billing export root.
- Reject files above `DEEPSEEK_BILLING_EXPORT_MAX_BYTES`, defaulting to a conservative local value.
- For ZIP files, read CSV entries through `ZipFile.open` only; never extract archive members to disk.
- Include `source_file_sha256`, `source_file_name`, and `schema_hash` in `--json` output without printing row values.

- [ ] **Step 4: Run the audit on a real DeepSeek export**

Run with a locally downloaded DeepSeek Usage export ZIP or extracted directory:

```bash
python scripts/audit_deepseek_usage_export.py "$DEEPSEEK_USAGE_EXPORT_PATH" --json > /tmp/deepseek_usage_export_headers.json
```

Expected: `/tmp/deepseek_usage_export_headers.json` lists every CSV file and its headers without printing row values.

- [ ] **Step 5: Save the audit result**

Create `docs/qa/2026-06-03-deepseek-usage-export-schema-audit.md` with:

```markdown
# DeepSeek Usage Export Schema Audit

Date: 2026-06-03

Input: official DeepSeek Usage export ZIP or extracted directory, not committed.

## Files And Headers

Paste the output of:

    python scripts/audit_deepseek_usage_export.py "$DEEPSEEK_USAGE_EXPORT_PATH" --json

## Parser Decision

- The amount CSV is the monthly monetary authority.
- A redacted fixture must preserve real header names and use synthetic row values.
- If the export does not expose model, API key, amount, and currency semantics, implementation stops and the BI response reports `official_usage.status = "unsupported_export_schema"`.
```

- [ ] **Step 6: Create redacted fixture documentation**

Create `tests/fixtures/deepseek_usage_export/README.md`:

```markdown
# DeepSeek Usage Export Fixtures

Fixtures in this directory must preserve real DeepSeek export header names from `docs/qa/2026-06-03-deepseek-usage-export-schema-audit.md`.

Rules:

- Do not commit real API keys.
- Do not commit real amounts.
- Do not commit real timestamps if they can identify the account.
- Use synthetic row values while keeping real column names.
```

- [ ] **Step 7: Stop if no real schema is available**

Do not implement `DeepSeekBillingClient.parse_usage_export` until this task has produced the schema audit document and a redacted fixture plan.

## Task 0.5: Define Billing Scope, Cost Basis, And Billable Turn Contracts

**Files:**

- Create: `deeptutor/services/observability/provider_reconciliation.py`
- Test: `tests/services/test_provider_reconciliation.py`
- Modify: `.env.example`

- [x] **Step 1: Write scope and cost-basis tests**

Add tests that prove reconciliation refuses vague scope for margin decisions:

```python
from deeptutor.services.observability.provider_reconciliation import (
    BillingScope,
    CostBasis,
    ProviderAccountScope,
    fingerprint_secret,
)


def test_fingerprint_secret_never_returns_raw_key() -> None:
    fingerprint = fingerprint_secret("sk-real-secret-value")

    assert fingerprint
    assert "sk-real" not in fingerprint
    assert fingerprint != "sk-real-secret-value"


def test_billing_scope_rejects_unknown_margin_scope() -> None:
    scope = BillingScope(
        provider_name="deepseek",
        charged_account_fingerprint="",
        runtime_environment="unknown",
        cost_center="unknown",
        billing_cycle="2026-06",
        raw_model="deepseek-v4-flash",
        pricing_model="deepseek-v4-flash",
        billable_unit="conversation_turn",
    )

    assert scope.margin_confidence == "untrusted"
    assert "unknown_scope" in scope.warnings


def test_cost_basis_defaults_to_list_price_for_margin() -> None:
    basis = CostBasis.for_margin()

    assert basis.primary == "list_price_cost"
    assert "net_charge_cost" in basis.supporting


def test_provider_account_scope_matches_official_key_identity() -> None:
    scope = ProviderAccountScope(
        provider_name="deepseek",
        api_key_fingerprint="sha256:abc12345",
        official_key_id="key_123",
        official_key_label="prod-main",
    )

    assert scope.matches_official_key({"key_id": "key_123"}) is True
    assert scope.matches_official_key({"key_label": "prod-main"}) is True
    assert scope.matches_official_key({"key_id": "other"}) is False
```

- [x] **Step 2: Implement small provider-neutral primitives**

In `provider_reconciliation.py`, define:

```python
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class BillingScope:
    provider_name: str
    charged_account_fingerprint: str
    runtime_environment: str
    cost_center: str
    billing_cycle: str
    raw_model: str = ""
    normalized_model: str = ""
    pricing_model: str = ""
    billable_unit: str = "non_billable"
    billable_turn_id: str = ""

    @property
    def warnings(self) -> list[str]:
        warnings: list[str] = []
        if not self.charged_account_fingerprint:
            warnings.append("missing_account_scope")
        if self.runtime_environment in {"", "unknown"} or self.cost_center in {"", "unknown"}:
            warnings.append("unknown_scope")
        if self.billable_unit == "conversation_turn" and not self.billable_turn_id:
            warnings.append("missing_billable_turn_id")
        return warnings

    @property
    def margin_confidence(self) -> str:
        return "untrusted" if self.warnings else "trusted"


@dataclass(frozen=True, slots=True)
class CostBasis:
    primary: str
    supporting: tuple[str, ...] = ()

    @classmethod
    def for_margin(cls) -> "CostBasis":
        return cls(primary="list_price_cost", supporting=("net_charge_cost", "cash_paid_cost"))


@dataclass(slots=True)
class ProviderAccountScope:
    provider_name: str
    api_key_fingerprint: str = ""
    official_key_id: str = ""
    official_key_label: str = ""
    official_masked_key: str = ""

    def matches_official_key(self, official_row: dict[str, Any]) -> bool:
        candidates = {
            str(official_row.get("key_id") or "").strip(),
            str(official_row.get("key_label") or "").strip(),
            str(official_row.get("masked_key") or "").strip(),
            str(official_row.get("api_key_fingerprint") or "").strip(),
        }
        expected = {
            self.official_key_id,
            self.official_key_label,
            self.official_masked_key,
            self.api_key_fingerprint,
        }
        return bool({value for value in expected if value} & {value for value in candidates if value})
```

Also add `fingerprint_secret(value: str) -> str` using SHA-256 and returning only a short prefix. Do not accept or return raw API keys in public payloads.

- [x] **Step 3: Document runtime defaults**

Append to `.env.example`:

```dotenv
# Optional: usage/cost attribution scope
LLM_USAGE_RUNTIME_ENVIRONMENT=production
LLM_USAGE_COST_CENTER=prod_user_chat
DEEPSEEK_BILLING_KEY_ID=
DEEPSEEK_BILLING_KEY_LABEL=
DEEPSEEK_BILLING_MASKED_KEY=
```

- [x] **Step 4: Run scope tests**

Run:

```bash
pytest tests/services/test_provider_reconciliation.py::test_fingerprint_secret_never_returns_raw_key \
  tests/services/test_provider_reconciliation.py::test_billing_scope_rejects_unknown_margin_scope \
  tests/services/test_provider_reconciliation.py::test_cost_basis_defaults_to_list_price_for_margin \
  tests/services/test_provider_reconciliation.py::test_provider_account_scope_matches_official_key_identity -q
```

Expected: PASS after implementation.

## Task 1: Add Runtime Attribution Guardrails

**Files:**

- Modify: `deeptutor/tutorbot/providers/openai_compat_provider.py`
- Modify: `deeptutor/services/observability/langfuse_adapter.py`
- Test: `tests/services/test_langfuse_observability.py`
- Test: `tests/tutorbot/providers/test_openai_compat_provider_usage.py`

- [x] **Step 1: Write test that provider metadata reaches UsageLedger**

Add to `tests/services/test_langfuse_observability.py`:

```python
def test_record_usage_keeps_charged_provider_and_api_base() -> None:
    adapter = LangfuseObservability()
    fake_ledger = _FakeUsageLedger()
    adapter._usage_ledger = fake_ledger

    adapter.record_usage(
        usage_details={"input": 10.0, "output": 2.0, "total": 12.0},
        cost_details={"total": 0.001},
        source="provider",
        model="deepseek-v4-flash",
        metadata={
            "provider_name": "deepseek",
            "charged_provider_name": "deepseek",
            "requested_provider_name": "deepseek",
            "api_base": "https://api.deepseek.com",
            "effective_url": "https://api.deepseek.com",
            "api_key_fingerprint": "sha256:synthetic",
            "runtime_environment": "production",
            "cost_center": "prod_user_chat",
            "billable_unit": "conversation_turn",
            "billable_turn_id": "turn-1",
            "raw_model": "deepseek-v4-flash",
            "pricing_model": "deepseek-v4-flash",
        },
    )

    assert fake_ledger.calls[0]["metadata"]["provider_name"] == "deepseek"
    assert fake_ledger.calls[0]["metadata"]["charged_provider_name"] == "deepseek"
    assert fake_ledger.calls[0]["metadata"]["cost_center"] == "prod_user_chat"
    assert fake_ledger.calls[0]["metadata"]["billable_turn_id"] == "turn-1"
    assert fake_ledger.calls[0]["metadata"]["api_base"] == "https://api.deepseek.com"
```

- [x] **Step 2: Add provider metadata helper test**

Add to `tests/tutorbot/providers/test_openai_compat_provider_usage.py`:

```python
from deeptutor.tutorbot.providers.openai_compat_provider import OpenAICompatProvider
from deeptutor.services.provider_registry import find_by_name


def test_openai_compat_provider_builds_charged_provider_metadata() -> None:
    provider = OpenAICompatProvider(
        api_key="sk-test",
        api_base="https://api.deepseek.com",
        default_model="deepseek-v4-flash",
        spec=find_by_name("deepseek"),
        provider_name="deepseek",
    )

    metadata = provider._provider_metadata(streaming=False, model="deepseek-v4-flash")

    assert metadata["provider_name"] == "deepseek"
    assert metadata["charged_provider_name"] == "deepseek"
    assert metadata["requested_provider_name"] == "deepseek"
    assert metadata["api_base"] == "https://api.deepseek.com"
    assert metadata["effective_url"] == "https://api.deepseek.com"
    assert metadata["streaming"] is False
    assert metadata["runtime_environment"] in {"production", "staging", "local", "test", "unknown"}
    assert metadata["cost_center"]
    assert metadata["raw_model"] == "deepseek-v4-flash"
    assert metadata["pricing_model"] == "deepseek-v4-flash"
    assert metadata["api_key_fingerprint"]
    assert "sk-test" not in metadata["api_key_fingerprint"]
```

- [x] **Step 3: Run failing attribution tests**

Run:

```bash
pytest tests/services/test_langfuse_observability.py::test_record_usage_keeps_charged_provider_and_api_base \
  tests/tutorbot/providers/test_openai_compat_provider_usage.py::test_openai_compat_provider_builds_charged_provider_metadata -q
```

Expected: FAIL because `_provider_metadata` does not exist and provider metadata is not standardized.

- [x] **Step 4: Implement provider metadata helper**

In `OpenAICompatProvider`, add:

```python
def _provider_metadata(self, *, streaming: bool, model: str | None = None) -> dict[str, Any]:
    provider_name = self._provider_name or (self._spec.name if self._spec else "openai_compat")
    effective_url = self.api_base or (self._spec.default_api_base if self._spec else "")
    raw_model = str(model or self.default_model or "").strip()
    return {
        "provider_name": provider_name,
        "charged_provider_name": provider_name,
        "requested_provider_name": provider_name,
        "api_base": effective_url,
        "effective_url": effective_url,
        "streaming": bool(streaming),
        "runtime_environment": os.getenv("LLM_USAGE_RUNTIME_ENVIRONMENT", "unknown"),
        "cost_center": os.getenv("LLM_USAGE_COST_CENTER", "unknown"),
        "raw_model": raw_model,
        "normalized_model": raw_model,
        "pricing_model": _normalize_pricing_model(raw_model),
        "api_key_fingerprint": fingerprint_secret(self.api_key or ""),
    }
```

Import `os`, `fingerprint_secret`, and a small `_normalize_pricing_model` helper. The model normalizer must preserve `raw_model` in metadata and only map aliases for pricing, with a comment pointing back to the DeepSeek pricing doc and `pricing_source_checked_at`.

Use this helper at every `start_observation` and `update_observation` call in `OpenAICompatProvider`.

- [x] **Step 5: Run attribution tests**

Run:

```bash
pytest tests/services/test_langfuse_observability.py::test_record_usage_keeps_charged_provider_and_api_base \
  tests/tutorbot/providers/test_openai_compat_provider_usage.py::test_openai_compat_provider_builds_charged_provider_metadata -q
```

Expected: PASS.

## Task 1.5: Bind Provider Usage To Real Wallet Capture

**Files:**

- Modify: `deeptutor/services/observability/usage_ledger.py`
- Modify: `deeptutor/services/session/turn_runtime.py`
- Test: `tests/services/test_usage_ledger.py`
- Test: `tests/api/test_unified_ws_turn_runtime.py`

- [x] **Step 1: Write the failing ledger binding test**

Add to `tests/services/test_usage_ledger.py`:

```python
def test_usage_ledger_marks_turn_billable_only_after_wallet_capture(tmp_path) -> None:
    ledger = UsageLedger(db_path=tmp_path / "llm_usage.db")

    ledger.record_usage_event(
        usage_source="provider",
        usage_details={"input": 10.0, "output": 5.0, "total": 15.0},
        cost_details={"total": 0.02},
        model="deepseek-v4-flash",
        metadata={
            "provider_name": "deepseek",
            "charged_provider_name": "deepseek",
            "runtime_environment": "production",
            "cost_center": "prod_user_chat",
        },
        session_id="session-1",
        turn_id="turn-1",
        scope_id="turn-1",
    )

    before = ledger.get_totals(
        start_ts=0,
        end_ts=9_999_999_999,
        provider_name="deepseek",
        billable_only=True,
    )
    assert before.total_tokens == 0

    updated = ledger.mark_turn_billable(
        turn_id="turn-1",
        billing_capture={
            "status": "captured",
            "idempotency_key": "mini_program_capture:turn-1",
            "amount_points": 20,
            "billing_amount_source": "fallback_minimum",
        },
    )

    assert updated == 1
    after = ledger.get_totals(
        start_ts=0,
        end_ts=9_999_999_999,
        provider_name="deepseek",
        billable_only=True,
    )
    assert after.billable_turns == 1
    assert after.provider_calls == 1
    assert after.total_tokens == 15
```

- [x] **Step 2: Run the failing ledger binding test**

Run:

```bash
pytest tests/services/test_usage_ledger.py::test_usage_ledger_marks_turn_billable_only_after_wallet_capture -q
```

Expected: FAIL because `mark_turn_billable` and `billable_only` do not exist.

- [x] **Step 3: Implement `UsageLedger.mark_turn_billable`**

Add a method that updates existing rows for the same turn after wallet capture succeeds:

```python
def mark_turn_billable(self, *, turn_id: str, billing_capture: dict[str, Any]) -> int:
    resolved_turn_id = _as_str(turn_id)
    if not resolved_turn_id:
        return 0
    if str((billing_capture or {}).get("status") or "") != "captured":
        return 0

    updated = 0
    with self._lock:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, metadata_json
                FROM llm_usage_events
                WHERE turn_id = ? OR scope_id = ?
                """,
                (resolved_turn_id, resolved_turn_id),
            ).fetchall()
            for row in rows:
                try:
                    metadata = json.loads(row["metadata_json"] or "{}")
                except json.JSONDecodeError:
                    metadata = {}
                metadata.update(
                    {
                        "billable_unit": "conversation_turn",
                        "billable_turn_id": resolved_turn_id,
                        "billing_capture_status": "captured",
                        "billing_capture_idempotency_key": _as_str(
                            billing_capture.get("idempotency_key")
                        ),
                        "billing_reference_id": resolved_turn_id,
                        "billing_amount_points": _safe_int(billing_capture.get("amount_points")),
                        "billing_amount_source": _as_str(
                            billing_capture.get("billing_amount_source")
                        ),
                    }
                )
                conn.execute(
                    "UPDATE llm_usage_events SET metadata_json = ? WHERE id = ?",
                    (json.dumps(metadata, ensure_ascii=False, default=str), row["id"]),
                )
                updated += 1
            conn.commit()
    return updated
```

This mirrors wallet capture evidence into the usage ledger. It does not become the wallet authority.

- [x] **Step 4: Call the binding method after successful mini-program capture**

In `turn_runtime.py`, immediately after `_capture_mobile_points` returns a captured payload, call:

```python
if billing_capture and billing_capture.get("status") == "captured":
    with contextlib.suppress(Exception):
        observability._usage_ledger.mark_turn_billable(
            turn_id=turn_id,
            billing_capture=billing_capture,
        )
```

If accessing `_usage_ledger` directly is too brittle, add a small public method on `LangfuseObservability`:

```python
def mark_usage_scope_billable(self, *, turn_id: str, billing_capture: dict[str, Any]) -> int:
    return self._usage_ledger.mark_turn_billable(
        turn_id=turn_id,
        billing_capture=billing_capture,
    )
```

Prefer the public method if this patch touches `LangfuseObservability` anyway.

- [x] **Step 5: Write the turn-runtime binding test**

Extend the existing mini-program capture test in `tests/api/test_unified_ws_turn_runtime.py` by monkeypatching `observability.mark_usage_scope_billable`:

```python
marked_billable: dict[str, Any] = {}

def fake_mark_usage_scope_billable(*, turn_id: str, billing_capture: dict[str, Any]) -> int:
    marked_billable["turn_id"] = turn_id
    marked_billable["billing_capture"] = dict(billing_capture)
    return 1

monkeypatch.setattr(
    "deeptutor.services.session.turn_runtime.observability.mark_usage_scope_billable",
    fake_mark_usage_scope_billable,
)

# Execute the same runtime.start_turn flow already used by the mini-program capture test.

assert marked_billable["turn_id"] == turn["id"]
assert marked_billable["billing_capture"]["status"] == "captured"
assert marked_billable["billing_capture"]["idempotency_key"] == f"mini_program_capture:{turn['id']}"
```

Use the existing wallet-service test fakes in this file instead of constructing a real wallet service.

- [x] **Step 6: Run binding tests**

Run:

```bash
pytest tests/services/test_usage_ledger.py::test_usage_ledger_marks_turn_billable_only_after_wallet_capture \
  tests/api/test_unified_ws_turn_runtime.py::test_turn_runtime_marks_usage_scope_billable_after_wallet_capture -q
```

Expected: PASS.

## Task 2: Preserve DeepSeek Cache Usage Fields

**Files:**

- Modify: `deeptutor/tutorbot/providers/openai_compat_provider.py:331`
- Modify: `deeptutor/tutorbot/providers/base.py:176`
- Test: `tests/tutorbot/providers/test_openai_compat_provider_usage.py`

- [x] **Step 1: Write the failing usage extraction test**

Add a test that proves provider-specific usage fields survive extraction.

```python
from deeptutor.tutorbot.providers.openai_compat_provider import OpenAICompatProvider


def test_extract_usage_preserves_deepseek_cache_tokens() -> None:
    response = {
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 200,
            "total_tokens": 1200,
            "prompt_cache_hit_tokens": 750,
            "prompt_cache_miss_tokens": 250,
        }
    }

    assert OpenAICompatProvider._extract_usage(response) == {
        "prompt_tokens": 1000,
        "completion_tokens": 200,
        "total_tokens": 1200,
        "prompt_cache_hit_tokens": 750,
        "prompt_cache_miss_tokens": 250,
    }
```

- [x] **Step 2: Run the failing test**

Run:

```bash
pytest tests/tutorbot/providers/test_openai_compat_provider_usage.py::test_extract_usage_preserves_deepseek_cache_tokens -q
```

Expected: FAIL because `_extract_usage` drops cache fields.

- [x] **Step 3: Preserve safe numeric usage keys**

Update `_extract_usage` to copy known numeric fields:

```python
usage_keys = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "prompt_cache_hit_tokens",
    "prompt_cache_miss_tokens",
)
return {key: int(usage_map.get(key) or 0) for key in usage_keys}
```

For object-style usage, use `getattr(usage_obj, key, 0)`.

- [x] **Step 4: Normalize cache fields into `usage_details`**

Extend `LLMProvider._normalize_usage_details` so it returns:

```python
{
    "input": prompt_tokens,
    "output": completion_tokens,
    "total": total_tokens,
    "input_cache_hit": float(usage.get("prompt_cache_hit_tokens") or 0.0),
    "input_cache_miss": float(usage.get("prompt_cache_miss_tokens") or 0.0),
}
```

Only include `input_cache_hit` and `input_cache_miss` when at least one is greater than zero.

- [x] **Step 5: Run provider usage tests**

Run:

```bash
pytest tests/tutorbot/providers/test_openai_compat_provider_usage.py -q
```

Expected: PASS.

## Task 3: Make DeepSeek Cost Estimation Cache-Aware

**Files:**

- Modify: `deeptutor/services/observability/langfuse_adapter.py:36`
- Modify: `deeptutor/services/observability/langfuse_adapter.py:200`
- Test: `tests/services/test_langfuse_observability.py`

- [ ] **Step 1: Write the failing cache-aware cost test**

Add:

```python
def test_deepseek_v4_flash_cost_uses_cache_hit_and_miss_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LANGFUSE_MODEL_PRICING_JSON", raising=False)
    adapter = LangfuseObservability()

    assert adapter.estimate_cost_details(
        model="deepseek-v4-flash",
        usage_details={
            "input": 1_000_000.0,
            "input_cache_hit": 800_000.0,
            "input_cache_miss": 200_000.0,
            "output": 100_000.0,
            "total": 1_100_000.0,
        },
    ) == {
        "input": 0.03024,
        "output": 0.028,
        "total": 0.05824,
    }
```

Calculation uses official DeepSeek v4 flash USD pricing checked on 2026-06-03:

- cache hit input: `800000 / 1_000_000 * 0.0028 = 0.00224`
- cache miss input: `200000 / 1_000_000 * 0.14 = 0.028`
- output: `100000 / 1_000_000 * 0.28 = 0.028`

- [ ] **Step 2: Run the failing test**

Run:

```bash
pytest tests/services/test_langfuse_observability.py::test_deepseek_v4_flash_cost_uses_cache_hit_and_miss_tokens -q
```

Expected: FAIL because current pricing only multiplies total input by cache-miss input price.

- [ ] **Step 3: Add cache-aware pricing fields**

Represent DeepSeek pricing as:

```python
"deepseek-v4-flash": {
    "input_cache_hit_per_1m": 0.0028,
    "input_cache_miss_per_1m": 0.14,
    "output_per_1m": 0.28,
    "currency": "USD",
    "source": "deepseek-official-2026-06-03",
    "pricing_source_checked_at": "2026-06-03",
}
```

Keep existing `input_per_1m` aliases only for non-cache-aware fallback.

- [ ] **Step 4: Update `estimate_model_cost`**

When `usage_details` has cache fields and pricing has cache fields, compute:

```python
hit_units = float(usage_details.get("input_cache_hit") or 0.0)
miss_units = float(usage_details.get("input_cache_miss") or 0.0)
input_cost = (
    hit_units / 1_000_000.0 * float(pricing.get("input_cache_hit_per_1m") or 0.0)
    + miss_units / 1_000_000.0 * float(pricing.get("input_cache_miss_per_1m") or 0.0)
)
```

If cache fields are missing, fall back to `input_per_1m` so existing tests keep passing.

- [ ] **Step 5: Add pricing metadata helper**

Do not put string fields into `cost_details`. Add a metadata helper on `LangfuseObservability`:

```python
def pricing_metadata_for_model(self, model: str | None) -> dict[str, str]:
    pricing = self._pricing_for_model(model)
    currency = str(pricing.get("currency") or "").strip()
    checked_at = str(pricing.get("pricing_source_checked_at") or "").strip()
    source = str(pricing.get("source") or "").strip()
    metadata: dict[str, str] = {}
    if currency:
        metadata["pricing_currency"] = currency
        metadata["billing_currency"] = currency
    if checked_at:
        metadata["pricing_source_checked_at"] = checked_at
    if source:
        metadata["pricing_source"] = source
    return metadata
```

Whenever provider usage is recorded with locally priced cost details, merge this metadata into the ledger metadata. This keeps `cost_details: dict[str, float]` numeric while making currency rollups deterministic.

- [ ] **Step 6: Run Langfuse cost tests**

Run:

```bash
pytest tests/services/test_langfuse_observability.py -q
```

Expected: PASS.

## Task 4: Extend UsageLedger Rollups Without Creating a Second Schema Authority

**Files:**

- Modify: `deeptutor/services/observability/usage_ledger.py:34`
- Test: `tests/services/test_usage_ledger.py`

- [ ] **Step 1: Write the failing metadata rollup test**

Add:

```python
def test_usage_ledger_rolls_up_deepseek_cache_metadata(tmp_path) -> None:
    ledger = UsageLedger(db_path=tmp_path / "llm_usage.db")

    ledger.record_usage_event(
        usage_source="provider",
        usage_details={
            "input": 1000.0,
            "input_cache_hit": 700.0,
            "input_cache_miss": 300.0,
            "output": 200.0,
            "total": 1200.0,
        },
        cost_details={"input": 0.000044, "output": 0.000056, "total": 0.0001},
        model="deepseek-v4-flash",
        metadata={
            "provider_name": "deepseek",
            "charged_provider_name": "deepseek",
            "requested_provider_name": "deepseek",
            "api_key_fingerprint": "sha256:test",
            "runtime_environment": "production",
            "cost_center": "prod_user_chat",
            "billable_unit": "conversation_turn",
            "billable_turn_id": "turn-1",
            "raw_model": "deepseek-v4-flash",
            "pricing_model": "deepseek-v4-flash",
            "pricing_currency": "USD",
            "billing_currency": "USD",
            "pricing_source_checked_at": "2026-06-03",
            "official_usage_fields": {
                "prompt_cache_hit_tokens": 700,
                "prompt_cache_miss_tokens": 300,
            },
        },
    )

    totals = ledger.get_totals(start_ts=0, end_ts=9_999_999_999, provider_name="deepseek")

    assert totals.total_tokens == 1200
    assert totals.metadata_breakdown["input_cache_hit_tokens"] == 700
    assert totals.metadata_breakdown["input_cache_miss_tokens"] == 300
    assert totals.currency_amounts["USD"] == 0.0001
    assert totals.billable_turns == 1
    assert totals.provider_calls == 1
    assert totals.cost_center_amounts["prod_user_chat"]["USD"] == 0.0001
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
pytest tests/services/test_usage_ledger.py::test_usage_ledger_rolls_up_deepseek_cache_metadata -q
```

Expected: FAIL because `UsageLedgerTotals` has no metadata breakdown.

- [ ] **Step 3: Extend `UsageLedgerTotals`**

Add fields:

```python
metadata_breakdown: dict[str, int] = field(default_factory=dict)
currency_amounts: dict[str, float] = field(default_factory=dict)
provider_amounts: dict[str, float] = field(default_factory=dict)
```

Keep the existing `total_cost_usd` fields for backward compatibility, but do not treat them as provider-native truth.

- [ ] **Step 4: Persist raw usage and cost details in metadata**

Update `UsageLedger.record_usage_event` before writing `metadata_json`:

```python
if usage_details:
    payload.setdefault("usage_details", dict(usage_details))
if cost_details:
    payload.setdefault("cost_details", dict(cost_details))
if "billing_currency" not in payload:
    currency = str(payload.get("pricing_currency") or (cost_details or {}).get("currency") or "").strip()
    if currency:
        payload["billing_currency"] = currency
```

`cost_details["currency"]` is a legacy fallback only; new code should put `pricing_currency` and `billing_currency` in metadata. Do not store API keys, request bodies, prompts, completions, or raw export rows in `metadata_json`.

- [ ] **Step 5: Add billing-scope filters and billable-turn counters**

Extend `UsageLedger.get_totals` with optional filters:

```python
environment: str | None = None
cost_center: str | None = None
api_key_fingerprint: str | None = None
billable_only: bool = False
```

Because these fields live in `metadata_json`, keep SQL filtering to time/provider/model and apply the new filters while iterating rows. For narrow BI windows this is acceptable. If this becomes hot, add generated columns in a later migration.

Track:

```python
billable_turn_ids: set[str]
provider_calls: int
unattributed_provider_calls: int
cost_center_amounts: dict[str, dict[str, float]]
```

Expose `billable_turns = len(billable_turn_ids)` and `calls_per_billable_turn` in `UsageLedgerTotals.to_dict()`.

- [ ] **Step 6: Aggregate cache and currency from metadata**

Inside `get_totals`, parse `metadata_json` for provider-scoped rows and accumulate:

```python
metadata_breakdown["input_cache_hit_tokens"] += _safe_int(
    usage_details.get("input_cache_hit")
    or official_usage_fields.get("prompt_cache_hit_tokens")
)
metadata_breakdown["input_cache_miss_tokens"] += _safe_int(
    usage_details.get("input_cache_miss")
    or official_usage_fields.get("prompt_cache_miss_tokens")
)
currency_amounts[currency] += _safe_float(cost_details.get("total"))
```

Use row data and metadata only. Do not read Langfuse directly from `UsageLedger`.

- [ ] **Step 7: Run UsageLedger tests**

Run:

```bash
pytest tests/services/test_usage_ledger.py -q
```

Expected: PASS.

## Task 5: Add DeepSeek Official Billing Adapter

**Files:**

- Create: `deeptutor/services/observability/deepseek_billing.py`
- Test: `tests/services/test_deepseek_billing.py`
- Test Fixture: `tests/fixtures/deepseek_usage_export/amount_redacted.csv`
- Modify: `.env.example`

- [ ] **Step 1: Write balance client tests without network**

Add:

```python
from deeptutor.services.observability.deepseek_billing import (
    DeepSeekBalanceTotals,
    DeepSeekBillingConfig,
    DeepSeekBillingClient,
)


def test_deepseek_balance_totals_parse_official_payload() -> None:
    payload = {
        "is_available": True,
        "balance_infos": [
            {"currency": "CNY", "total_balance": "110.00", "granted_balance": "10.00", "topped_up_balance": "100.00"}
        ],
    }

    totals = DeepSeekBalanceTotals.from_payload(payload)

    assert totals.is_available is True
    assert totals.currency_balances["CNY"]["total_balance"] == 110.0
    assert totals.currency_balances["CNY"]["granted_balance"] == 10.0
    assert totals.currency_balances["CNY"]["topped_up_balance"] == 100.0
```

- [ ] **Step 2: Write usage export parser test from the redacted audited fixture**

Use `tests/fixtures/deepseek_usage_export/amount_redacted.csv`. The fixture must preserve real header names from `docs/qa/2026-06-03-deepseek-usage-export-schema-audit.md` and use synthetic values.

```python
def test_deepseek_usage_export_parser_aggregates_by_key_and_model(tmp_path) -> None:
    export = Path("tests/fixtures/deepseek_usage_export/amount_redacted.csv")

    totals = DeepSeekBillingClient.parse_usage_export(export)

    assert totals.total_amount == 0.0001
    assert totals.currency == "USD"
    assert totals.models["deepseek-v4-flash"]["input_cache_hit_tokens"] == 700
    assert totals.models["deepseek-v4-flash"]["input_cache_miss_tokens"] == 300
    assert totals.models["deepseek-v4-flash"]["output_tokens"] == 200
```

- [ ] **Step 3: Run failing tests**

Run:

```bash
pytest tests/services/test_deepseek_billing.py -q
```

Expected: FAIL because `deepseek_billing.py` does not exist.

- [ ] **Step 4: Implement the adapter**

Create dataclasses:

```python
@dataclass(slots=True)
class DeepSeekBillingConfig:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    usage_export_dir: str = ""


@dataclass(slots=True)
class DeepSeekUsageExportTotals:
    status: str = "unconfigured"
    total_amount: float = 0.0
    currency: str = "USD"
    currency_amounts: dict[str, float] = field(default_factory=dict)
    cost_basis: str = "net_charge_cost"
    models: dict[str, dict[str, float]] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)
```

Expose:

```python
class DeepSeekBillingClient:
    def is_configured(self) -> bool:
        return bool(self._config.api_key or self._config.usage_export_dir)

    async def get_balance(self) -> DeepSeekBalanceTotals:
        if not self._config.api_key:
            return DeepSeekBalanceTotals(status="unconfigured")
        return await self._fetch_balance()

    @staticmethod
    def parse_usage_export(path: Path) -> DeepSeekUsageExportTotals:
        return parse_deepseek_usage_export(path)

    async def get_usage_export_totals(
        self,
        *,
        billing_cycle: str | None = None,
        model: str | None = None,
    ) -> DeepSeekUsageExportTotals:
        if not self._config.usage_export_dir:
            return DeepSeekUsageExportTotals(status="unconfigured")
        return self.parse_usage_export(Path(self._config.usage_export_dir))
```

Only `get_balance` performs HTTP. `parse_usage_export` and `get_usage_export_totals` are file-based and deterministic. If the audited export schema cannot map model, amount, currency, and API key semantics, return `status="unsupported_export_schema"` instead of guessing.

The parser must return a manifest containing `source_file_sha256`, `schema_hash`, `billing_cycle`, and `imported_at`. Re-importing the same file hash for the same provider/cycle must produce the same totals and not duplicate any persisted import record.

- [ ] **Step 5: Document env vars**

Append to `.env.example`:

```dotenv
# Optional: official billing reconciliation
DEEPSEEK_BILLING_API_KEY=
DEEPSEEK_BILLING_BASE_URL=https://api.deepseek.com
DEEPSEEK_BILLING_USAGE_EXPORT_DIR=
DEEPSEEK_BILLING_EXPORT_MAX_BYTES=10485760
```

`DEEPSEEK_BILLING_API_KEY` may default to `DEEPSEEK_API_KEY` in code, but keep a separate env var to allow read-only billing keys if DeepSeek supports scoped keys later.

- [ ] **Step 6: Run DeepSeek billing tests**

Run:

```bash
pytest tests/services/test_deepseek_billing.py -q
```

Expected: PASS.

## Task 5.5: Persist Official Billing Import Manifests Idempotently

**Files:**

- Create: `deeptutor/services/observability/official_billing_imports.py`
- Test: `tests/services/test_official_billing_imports.py`

- [ ] **Step 1: Write the failing import idempotency test**

Add:

```python
from deeptutor.services.observability.official_billing_imports import OfficialBillingImportStore


def test_official_billing_import_store_is_idempotent_by_provider_cycle_and_hash(tmp_path) -> None:
    store = OfficialBillingImportStore(db_path=tmp_path / "official_billing_imports.db")

    first = store.record_import(
        provider_name="deepseek",
        billing_cycle="2026-06",
        source_file_sha256="abc123",
        schema_hash="schema123",
        source_file_name="usage.zip",
        manifest={"files": ["amount.csv"]},
    )
    second = store.record_import(
        provider_name="deepseek",
        billing_cycle="2026-06",
        source_file_sha256="abc123",
        schema_hash="schema123",
        source_file_name="usage.zip",
        manifest={"files": ["amount.csv"]},
    )

    assert first.inserted is True
    assert second.inserted is False
    assert second.import_id == first.import_id
    assert store.list_imports(provider_name="deepseek", billing_cycle="2026-06")[0].source_file_sha256 == "abc123"
```

- [ ] **Step 2: Run the failing import test**

Run:

```bash
pytest tests/services/test_official_billing_imports.py::test_official_billing_import_store_is_idempotent_by_provider_cycle_and_hash -q
```

Expected: FAIL because `official_billing_imports.py` does not exist.

- [ ] **Step 3: Implement the import manifest store**

Create:

```python
@dataclass(slots=True)
class OfficialBillingImportRecord:
    import_id: int
    provider_name: str
    billing_cycle: str
    source_file_sha256: str
    schema_hash: str
    source_file_name: str
    imported_at: float
    manifest: dict[str, Any]
    inserted: bool = False


class OfficialBillingImportStore:
    def __init__(self, db_path: Path | None = None) -> None:
        path_service = PathService.get_instance()
        self._db_path = (db_path or (path_service.get_user_root() / "official_billing_imports.db")).resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS official_billing_imports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_name TEXT NOT NULL,
                    billing_cycle TEXT NOT NULL,
                    source_file_sha256 TEXT NOT NULL,
                    schema_hash TEXT NOT NULL,
                    source_file_name TEXT NOT NULL,
                    imported_at REAL NOT NULL,
                    manifest_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(provider_name, billing_cycle, source_file_sha256)
                )
                """
            )
            conn.commit()
```

`record_import` must `INSERT OR IGNORE`, then read back the canonical row and return `inserted=False` for duplicate imports.

- [ ] **Step 4: Wire DeepSeek parser output to the manifest store**

In `DeepSeekBillingClient.get_usage_export_totals`, after parsing a configured export directory or ZIP, call the store only when parse status is usable:

```python
if totals.status in {"ok", "empty"} and totals.manifest.get("source_file_sha256"):
    self._import_store.record_import(
        provider_name="deepseek",
        billing_cycle=str(totals.manifest.get("billing_cycle") or billing_cycle or ""),
        source_file_sha256=str(totals.manifest["source_file_sha256"]),
        schema_hash=str(totals.manifest.get("schema_hash") or ""),
        source_file_name=str(totals.manifest.get("source_file_name") or ""),
        manifest=totals.manifest,
    )
```

Do not persist raw export rows.

- [ ] **Step 5: Run import tests**

Run:

```bash
pytest tests/services/test_official_billing_imports.py tests/services/test_deepseek_billing.py -q
```

Expected: PASS.

## Task 6: Normalize Provider Reconciliation Results

**Files:**

- Create: `deeptutor/services/observability/provider_reconciliation.py`
- Test: `tests/services/test_provider_reconciliation.py`

- [ ] **Step 1: Write delta tests**

Add:

```python
from deeptutor.services.observability.provider_reconciliation import build_reconciliation_delta


def test_build_reconciliation_delta_flags_large_official_gap() -> None:
    result = build_reconciliation_delta(
        provider_name="deepseek",
        cost_basis="list_price_cost",
        internal={
            "total_tokens": 1200,
            "currency_amounts": {"USD": 0.0001},
            "billable_turns": 1,
            "provider_calls": 1,
            "unattributed_provider_calls": 0,
        },
        official={
            "total_tokens": 1000,
            "currency_amounts": {"USD": 0.0002},
        },
        warn_ratio=0.05,
    )

    assert result["provider_name"] == "deepseek"
    assert result["cost_basis"] == "list_price_cost"
    assert result["token_delta"] == 200
    assert result["amount_delta_by_currency"]["USD"] == -0.0001
    assert result["status"] == "warning"
    assert result["cost_per_billable_turn"]["USD"] == 0.0001


def test_build_reconciliation_delta_refuses_cross_currency_amount_delta() -> None:
    result = build_reconciliation_delta(
        provider_name="deepseek",
        cost_basis="list_price_cost",
        internal={"total_tokens": 1200, "currency_amounts": {"USD": 0.0001}},
        official={"total_tokens": 1200, "currency_amounts": {"CNY": 0.0007}},
        warn_ratio=0.05,
    )

    assert result["status"] == "warning"
    assert result["amount_delta_by_currency"] == {}
    assert "currency_mismatch" in result["warnings"]
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
pytest tests/services/test_provider_reconciliation.py -q
```

Expected: FAIL because the helper does not exist.

- [ ] **Step 3: Implement provider-neutral delta helper**

Return a plain dict shaped for BI:

```json
{
    "provider_name": "deepseek",
    "status": "warning",
    "token_delta": 200,
    "token_delta_ratio": 0.2,
    "cost_basis": "list_price_cost",
    "cost_per_billable_turn": {
        "USD": 0.0001
    },
    "amount_delta_by_currency": {
        "USD": -0.0001
    },
    "warnings": ["currency_mismatch"],
    "confidence": "warning"
}
```

No provider-specific parsing belongs in this file.

Status rules in this helper:

- Return `currency_mismatch` when same-currency amount deltas cannot be calculated.
- Return `untrusted` when `unattributed_provider_calls / provider_calls > 0.05`.
- Return `waiting_for_official_export` when internal usage exists but official usage is unconfigured or empty for DeepSeek.
- Return `scope_mismatch` when internal and official account/key/workspace scope values disagree.
- Include `cost_basis` in every response so BI cannot silently mix margin and finance views.

- [ ] **Step 4: Run reconciliation helper tests**

Run:

```bash
pytest tests/services/test_provider_reconciliation.py -q
```

Expected: PASS.

## Task 7: Make BI Cost Reconciliation Provider-Aware

**Files:**

- Modify: `deeptutor/services/bi_service.py:2277`
- Modify: `deeptutor/api/routers/bi.py:170`
- Test: `tests/api/test_bi_router.py`

- [ ] **Step 1: Write router tests for `provider=deepseek` and admin-only access**

Add:

```python
def test_bi_cost_reconciliation_supports_deepseek_provider(bi_service: BIService) -> None:
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = lambda: {"role": "admin"}

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/bi/cost/reconciliation"
            "?days=30&provider=deepseek&billing_cycle=2026-06"
            "&environment=production&cost_center=prod_user_chat&billable_only=true"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filters"]["provider"] == "deepseek"
    assert "providers" in payload
    assert "deepseek" in payload["providers"]


def test_bi_cost_reconciliation_rejects_metrics_token_only(bi_service: BIService, monkeypatch) -> None:
    app = _build_app(bi_service)
    monkeypatch.setenv("DEEPTUTOR_BI_PUBLIC_ENABLED", "true")
    monkeypatch.setenv("DEEPTUTOR_METRICS_TOKEN", "metrics-secret")

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/bi/cost/reconciliation?provider=all&billing_cycle=2026-06",
            headers={"X-Metrics-Token": "metrics-secret"},
        )

    assert response.status_code == 403
```

- [ ] **Step 2: Run failing router tests**

Run:

```bash
pytest tests/api/test_bi_router.py::test_bi_cost_reconciliation_supports_deepseek_provider \
  tests/api/test_bi_router.py::test_bi_cost_reconciliation_rejects_metrics_token_only -q
```

Expected: FAIL because the endpoint does not accept provider-neutral output yet and does not enforce admin-only access.

- [ ] **Step 3: Add `provider` query parameter**

In `deeptutor/api/routers/bi.py`, pass `provider` into `BIService.get_cost_reconciliation`.

```python
@router.get("/cost/reconciliation")
async def get_cost_reconciliation(
    _auth: AuthContext = Depends(require_bi_admin),
    provider: str = Query("dashscope"),
    days: int = Query(30, ge=1, le=3650),
    capability: str | None = None,
    entrypoint: str | None = None,
    tier: str | None = None,
    environment: str | None = None,
    cost_center: str = Query("all"),
    billable_only: bool = Query(False),
    cost_basis: str = Query("list_price_cost"),
    workspace_id: str | None = None,
    apikey_id: str | None = None,
    api_key_fingerprint: str | None = None,
    model: str | None = None,
    billing_cycle: str | None = None,
) -> dict[str, Any]:
    return await service.get_cost_reconciliation(
        provider=provider,
        days=days,
        capability=capability,
        entrypoint=entrypoint,
        tier=tier,
        environment=environment,
        cost_center=cost_center,
        billable_only=billable_only,
        cost_basis=cost_basis,
        workspace_id=workspace_id,
        apikey_id=apikey_id,
        api_key_fingerprint=api_key_fingerprint,
        model=model,
        billing_cycle=billing_cycle,
    )
```

Default can remain `dashscope` for backward compatibility, but BI should explicitly call `provider=all` after P0.

- [ ] **Step 4: Refactor service output**

Change `BIService.get_cost_reconciliation` to support:

- `provider=deepseek`
- `provider=dashscope`
- `provider=all`

Expected top-level shape:

```python
{
    "filters": {
        "provider": "all",
        "days": 30,
        "billing_cycle": "2026-06",
        "model": "",
        "environment": "production",
        "cost_center": "prod_user_chat",
        "billable_only": True,
        "cost_basis": "list_price_cost",
    },
    "providers": {
        "deepseek": {
            "internal": {
                "total_tokens": 0,
                "currency_amounts": {},
                "billable_turns": 0,
                "provider_calls": 0,
                "calls_per_billable_turn": 0.0,
                "non_billable_cost": {},
                "unattributed_provider_calls": 0,
            },
            "official_usage": {"status": "unconfigured", "currency_amounts": {}},
            "official_balance": {"status": "unconfigured", "account_currency": ""},
            "reconciliation": {"status": "unconfigured", "warnings": []},
        },
        "dashscope": {
            "internal": {"total_tokens": 0, "currency_amounts": {}},
            "bailian": {"status": "unconfigured", "total_tokens": 0},
            "bailian_billing": {"status": "unconfigured", "currency_amounts": {}},
            "reconciliation": {"status": "unconfigured", "warnings": []},
        },
    },
    "warnings": [],
}
```

Keep legacy fields `bailian`, `bailian_billing`, `system_global_bailian`, and `reconciliation` when `provider=dashscope` so existing consumers do not break.

- [ ] **Step 5: Remove hard-coded `dashscope` from provider-neutral code**

Any usage ledger call must use the requested provider:

```python
system_global_totals = self._usage_ledger.get_totals(
    start_ts=window_start,
    end_ts=now_ts,
    provider_name=effective_provider,
    model=model,
    environment=environment,
    cost_center=None if cost_center == "all" else cost_center,
    api_key_fingerprint=api_key_fingerprint,
    billable_only=billable_only,
)
```

Only the Bailian-specific branch should use `dashscope`.

- [ ] **Step 6: Run API tests**

Run:

```bash
pytest tests/api/test_bi_router.py::test_bi_router_requires_admin_for_sensitive_endpoints \
  tests/api/test_bi_router.py::test_bi_cost_reconciliation_supports_deepseek_provider \
  tests/api/test_bi_router.py::test_bi_cost_reconciliation_rejects_metrics_token_only -q
```

Expected: PASS.

## Task 8: Keep Bailian Official Billing but Fit the Same Shape

**Files:**

- Modify: `deeptutor/services/observability/bailian_billing.py`
- Modify: `deeptutor/services/bi_service.py`
- Test: `tests/services/test_bailian_billing.py`
- Test: `tests/api/test_bi_router.py`

- [ ] **Step 1: Keep existing BssOpenApi aggregation tests passing**

Run:

```bash
pytest tests/services/test_bailian_billing.py -q
```

Expected: PASS before and after this task.

- [ ] **Step 2: Add provider-neutral `to_official_usage_dict`**

In `BailianBillingTotals`, expose:

```python
def to_official_usage_dict(self) -> dict[str, Any]:
    return {
        "status": "ok" if self.items_count else "empty",
        "provider_name": "dashscope",
        "cost_basis": "list_price_cost",
        "currency_amounts": {self.currency: round(float(self.pretax_amount or 0.0), 8)},
        "list_price_cost": {self.currency: round(float(self.pretax_amount or 0.0), 8)},
        "net_charge_cost": {self.currency: round(float(self.after_discount_amount or 0.0), 8)},
        "model_amounts": dict(self.model_amounts),
        "usage_kind_amounts": dict(self.usage_kind_amounts),
        "items_count": int(self.items_count),
    }
```

- [ ] **Step 3: Run Bailian and API tests**

Run:

```bash
pytest tests/services/test_bailian_billing.py tests/api/test_bi_router.py::test_bi_router_requires_admin_for_sensitive_endpoints -q
```

Expected: PASS.

## Task 9: Optional BI UI Projection After Backend Shape Is Stable

**Files:**

- Modify only if requested: `web/components/bi/*`
- Modify only if requested: `web/lib/member-api.ts`
- Test only if modified: existing BI frontend tests and Playwright smoke.

- [ ] **Step 1: Add UI only after backend response is stable**

Display provider cards:

- DeepSeek official
- Alibaba DashScope/Bailian
- Unknown/other provider calls

Each card shows internal amount, official amount, token delta, amount delta, currency, and warnings.

- [ ] **Step 2: Do not hide `unconfigured`**

If DeepSeek export or Bailian BssOpenApi is unconfigured, show `unconfigured` explicitly. A missing official connector is a risk state, not a green state.

- [ ] **Step 3: Run frontend verification**

Run the repo's existing BI frontend test/smoke commands used for BI changes. If no narrow UI test exists for this surface, add a small API contract test first and then run Playwright only for the affected BI route.

## Acceptance Criteria

P0 is complete only when all are true:

- `UsageLedger` can report provider-specific totals for `deepseek` and `dashscope`.
- `UsageLedger` can report totals by provider, environment, cost center, API-key fingerprint, model, and billable-turn scope.
- Provider usage becomes package-margin eligible only after wallet capture marks the turn billable.
- DeepSeek cache hit/miss fields are preserved from provider response to usage details.
- DeepSeek cost estimation uses cache hit/miss official pricing when available.
- Currency metadata is carried in `pricing_currency` / `billing_currency` metadata, not as string fields inside numeric `cost_details`.
- `/api/v1/bi/cost/reconciliation?provider=deepseek` returns internal ledger totals and official DeepSeek balance/export status.
- `/api/v1/bi/cost/reconciliation` requires BI admin access; metrics-token-only and BI-public access are rejected.
- `/api/v1/bi/cost/reconciliation?provider=dashscope` keeps existing Bailian behavior and legacy response compatibility.
- `/api/v1/bi/cost/reconciliation?provider=all` returns separate DeepSeek and DashScope provider blocks.
- BI exposes `list_price_cost`, `net_charge_cost`, and selected `cost_basis`; package-margin views default to `list_price_cost`.
- BI exposes `billable_turns`, `provider_calls`, `calls_per_billable_turn`, `list_price_cost_per_billable_turn`, `non_billable_cost`, and `unattributed_provider_calls` for margin queries.
- Unknown `environment`, `cost_center`, API-key scope, or missing `billable_turn_id` creates at least `warning`; more than 5% unattributed provider calls creates `untrusted`.
- If any DashScope/Bailian official bill exists while the declared production default is DeepSeek, the response includes a warning.
- DeepSeek amount deltas are calculated from official Usage export, not from `/user/balance`.
- Cross-currency official/internal amounts are shown as `currency_mismatch` and are not subtracted.
- Raw official export files are ignored by git; committed fixtures are redacted and synthetic; import manifests include file hash and schema hash.
- Official billing imports are idempotent by provider, billing cycle, and source file hash.
- Official export parser rejects unsupported schema and unsafe paths instead of guessing.
- Tests pass:

```bash
pytest tests/tutorbot/providers/test_openai_compat_provider_usage.py \
  tests/services/test_usage_ledger.py \
  tests/services/test_langfuse_observability.py \
  tests/services/test_deepseek_billing.py \
  tests/services/test_official_billing_imports.py \
  tests/services/test_provider_reconciliation.py \
  tests/services/test_bailian_billing.py \
  tests/api/test_bi_router.py -q
```

## Operational Runbook

Daily or weekly finance check:

1. Query BI reconciliation for all providers:

```bash
curl -H "Authorization: Bearer $BI_ADMIN_TOKEN" \
  "https://<host>/api/v1/bi/cost/reconciliation?provider=all&days=30&billing_cycle=YYYY-MM"
```

Package-margin check for 次卡 design:

```bash
curl -H "Authorization: Bearer $BI_ADMIN_TOKEN" \
  "https://<host>/api/v1/bi/cost/reconciliation?provider=all&billing_cycle=YYYY-MM&environment=production&cost_center=prod_user_chat&billable_only=true&cost_basis=list_price_cost"
```

Use this package-margin query, not the all-cost finance query, when deciding how many conversations 198/698 packages can sustainably include.

2. For DeepSeek:

- Call `/user/balance` through the adapter only to verify account availability and account currency.
- Place the official monthly Usage export under `DEEPSEEK_BILLING_USAGE_EXPORT_DIR`, which must point to an ignored local/runtime directory, not a committed fixture directory.
- Re-run reconciliation.

3. For Alibaba:

- Ensure `BAILIAN_BILLING_ACCESS_KEY_ID`, `BAILIAN_BILLING_ACCESS_KEY_SECRET`, `BAILIAN_BILLING_WORKSPACE_ID`, and `BAILIAN_BILLING_APIKEY_ID` are configured.
- Use `billing_cycle=YYYY-MM` for precise official amount comparison.

4. Investigate warnings in this order:

- Provider drift: internal ledger has `dashscope` while production default says `deepseek`.
- Export gap: DeepSeek usage export missing or wrong month.
- Currency mismatch: local estimate and official export use different currencies, so amount delta is unavailable until pricing/export currencies are aligned.
- Scope mismatch: API-key fingerprint, workspace, environment, or cost center does not match the official export scope.
- Billable attribution gap: provider calls exist without `billable_turn_id`, so per-conversation cost is not trusted.
- Cost basis mismatch: finance net charge is being used where sustainable list-price margin is required.
- Current-month lag: Alibaba official bill can lag and current month can change before final settlement.
- Cache mismatch: DeepSeek internal estimate lacks cache hit/miss fields.

## Self-Review

- Placeholder scan: no unresolved placeholder term or empty implementation section remains.
- Scope check: P0 is backend/provider reconciliation; BI UI is explicitly P1/optional.
- Authority check: `UsageLedger` remains internal authority; official provider adapters only supply external truth.
- Provider drift check: DeepSeek default does not imply Alibaba is irrelevant; fallback and existing DashScope support keep Alibaba in scope.
- Currency check: provider-native currencies are preserved; no hidden USD/CNY conversion is introduced.
- Review fix check: v0.2 adds real DeepSeek export schema audit, downgrades balance to snapshot evidence, front-loads provider attribution, removes ambiguous placeholder snippets, and adds raw export safety boundaries.
- Margin-hardening check: v0.3 separates list-price, net-charge, and cash-paid cost; adds billing scope, cost center, runtime environment, API-key fingerprint, and billable-turn attribution so BI can support package margin decisions rather than only provider spend reporting.
- Scenario check: v0.3 explicitly covers month-end close, daily finance checks, package margin, fallback drift, eval contamination, API-key rotation, export schema drift, and stale pricing.
- Review fix check: v0.4 fixes the second review blockers by adding admin-only access, wallet-capture-based billable turn binding, provider account scope mapping, import manifest persistence/idempotency, currency metadata closure, and P0A/P0B sequencing that does not block internal measurement on a missing DeepSeek export.

## GSTACK REVIEW REPORT

- Step 0 scope: HOLD SCOPE. No BI UI expansion, no automated console scraping, no FX conversion, and no wallet/package behavior changes.
- Plan-eng review fixes applied: admin-only route gate, true wallet capture binding, DeepSeek key identity mapping, persistent import manifest, numeric `cost_details` with currency metadata, and non-blocking P0A sequencing.
- Plan-ceo review fixes applied: package-margin evidence now requires `production + prod_user_chat + billable_only + list_price_cost` and real wallet capture, not provider-call counts alone.
- Remaining uncertainty: DeepSeek export headers still require a real official export audit before amount parser implementation can be trusted.
