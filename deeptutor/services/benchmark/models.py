"""Benchmark registry models."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

ALLOWED_CONTRACT_DOMAINS = {
    "routing_contract",
    "grounding_contract",
    "continuity_contract",
    "surface_contract",
    "production_replay_contract",
}

ALLOWED_CASE_TIERS = {
    "gate_stable",
    "regression_tier",
    "exploratory",
    "incident_replay",
}

ALLOWED_EXECUTION_KINDS = {
    "static_contract_eval",
    "live_ws_replay",
    "surface_parity_eval",
}

ALLOWED_FAILURE_TAXONOMY_SCOPE = {
    "FAIL_ROUTE_WRONG",
    "FAIL_CONTEXT_LOSS",
    "FAIL_GROUNDEDNESS",
    "FAIL_CONTINUITY",
    "FAIL_SURFACE_DELIVERY",
}

ALLOWED_ORIGIN_TYPES = {
    "seed_fixture",
    "legacy_replay",
    "surface_smoke",
    "incident_replay",
    "production_trace",
    "manual",
}

ALLOWED_PROMOTION_STATUSES = {
    "seed",
    "candidate",
    "promoted",
}


def _coerce_string(value: Any, *, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _coerce_scope(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    items = [value] if isinstance(value, str) else list(value)
    scope: list[str] = []
    for raw_item in items:
        item = _coerce_string(raw_item, field_name="failure_taxonomy_scope item")
        if item not in ALLOWED_FAILURE_TAXONOMY_SCOPE:
            raise ValueError(f"Unsupported failure_taxonomy_scope value: {item}")
        scope.append(item)
    return tuple(scope)


def _coerce_case_ids(value: Any) -> tuple[str, ...]:
    if value is None:
        raise ValueError("case_ids must not be missing")
    items = [value] if isinstance(value, str) else list(value)
    case_ids = tuple(_coerce_string(item, field_name="case_id") for item in items)
    if not case_ids:
        raise ValueError("case_ids must not be empty")
    return case_ids


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """Single benchmark case metadata entry."""

    dataset_id: str
    dataset_version: str
    case_id: str
    contract_domain: str
    case_tier: str
    execution_kind: str
    surface: str
    expected_contract: str
    failure_taxonomy_scope: tuple[str, ...] = field(default_factory=tuple)
    # Source reference path; may point to a fixture file or a script entrypoint.
    source_fixture: str = ""
    origin_type: str = "seed_fixture"
    origin_ref: str = ""
    promotion_status: str = "seed"
    promoted_from_case_id: str = ""

    def __post_init__(self) -> None:
        _coerce_string(self.dataset_id, field_name="dataset_id")
        _coerce_string(self.dataset_version, field_name="dataset_version")
        _coerce_string(self.case_id, field_name="case_id")
        if self.contract_domain not in ALLOWED_CONTRACT_DOMAINS:
            raise ValueError(f"Unsupported contract_domain: {self.contract_domain}")
        if self.case_tier not in ALLOWED_CASE_TIERS:
            raise ValueError(f"Unsupported case_tier: {self.case_tier}")
        if self.execution_kind not in ALLOWED_EXECUTION_KINDS:
            raise ValueError(f"Unsupported execution_kind: {self.execution_kind}")
        _coerce_string(self.surface, field_name="surface")
        _coerce_string(self.expected_contract, field_name="expected_contract")
        _coerce_string(self.source_fixture, field_name="source_fixture")
        if self.origin_type not in ALLOWED_ORIGIN_TYPES:
            raise ValueError(f"Unsupported origin_type: {self.origin_type}")
        if self.promotion_status not in ALLOWED_PROMOTION_STATUSES:
            raise ValueError(f"Unsupported promotion_status: {self.promotion_status}")
        if self.origin_ref:
            _coerce_string(self.origin_ref, field_name="origin_ref")
        if self.promoted_from_case_id:
            _coerce_string(self.promoted_from_case_id, field_name="promoted_from_case_id")

    @property
    def is_incident_promoted(self) -> bool:
        return self.origin_type == "incident_replay"

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BenchmarkCase":
        return cls(
            dataset_id=_coerce_string(payload["dataset_id"], field_name="dataset_id"),
            dataset_version=_coerce_string(
                payload["dataset_version"], field_name="dataset_version"
            ),
            case_id=_coerce_string(payload["case_id"], field_name="case_id"),
            contract_domain=_coerce_string(
                payload["contract_domain"], field_name="contract_domain"
            ),
            case_tier=_coerce_string(payload["case_tier"], field_name="case_tier"),
            execution_kind=_coerce_string(
                payload["execution_kind"], field_name="execution_kind"
            ),
            surface=_coerce_string(payload["surface"], field_name="surface"),
            expected_contract=_coerce_string(
                payload["expected_contract"], field_name="expected_contract"
            ),
            failure_taxonomy_scope=_coerce_scope(payload.get("failure_taxonomy_scope")),
            source_fixture=_coerce_string(payload["source_fixture"], field_name="source_fixture"),
            origin_type=_coerce_string(payload.get("origin_type", "seed_fixture"), field_name="origin_type"),
            origin_ref=str(payload.get("origin_ref", "") or "").strip(),
            promotion_status=_coerce_string(
                payload.get("promotion_status", "seed"),
                field_name="promotion_status",
            ),
            promoted_from_case_id=str(payload.get("promoted_from_case_id", "") or "").strip(),
        )


@dataclass(frozen=True, slots=True)
class BenchmarkSuite:
    """Grouped suite metadata for benchmark cases."""

    case_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_ids", _coerce_case_ids(self.case_ids))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BenchmarkSuite":
        if "case_ids" not in payload:
            raise ValueError("case_ids must not be missing")
        return cls(case_ids=_coerce_case_ids(payload["case_ids"]))


@dataclass(frozen=True, slots=True)
class BenchmarkRegistry:
    """Canonical benchmark registry payload."""

    version: str
    dataset_id: str
    dataset_version: str
    cases: Mapping[str, BenchmarkCase] = field(default_factory=dict)
    suites: Mapping[str, BenchmarkSuite] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _coerce_string(self.version, field_name="version")
        _coerce_string(self.dataset_id, field_name="dataset_id")
        _coerce_string(self.dataset_version, field_name="dataset_version")
        object.__setattr__(self, "cases", MappingProxyType(dict(self.cases)))
        object.__setattr__(self, "suites", MappingProxyType(dict(self.suites)))

    @property
    def suite_names(self) -> tuple[str, ...]:
        return tuple(self.suites.keys())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BenchmarkRegistry":
        version = _coerce_string(payload["version"], field_name="version")
        dataset_id = _coerce_string(payload["dataset_id"], field_name="dataset_id")
        dataset_version = _coerce_string(
            payload["dataset_version"], field_name="dataset_version"
        )

        raw_cases = payload["cases"]
        if not isinstance(raw_cases, Mapping):
            raise TypeError("cases must be a mapping")
        cases: dict[str, BenchmarkCase] = {}
        for case_id, case_payload in raw_cases.items():
            case_key = _coerce_string(case_id, field_name="case_id")
            case = BenchmarkCase.from_dict(case_payload)
            if case.case_id != case_key:
                raise ValueError(f"case_id mismatch: {case_key} != {case.case_id}")
            if case.dataset_id != dataset_id:
                raise ValueError(f"case dataset_id mismatch: {case.case_id}")
            if case.dataset_version != dataset_version:
                raise ValueError(f"case dataset_version mismatch: {case.case_id}")
            cases[case_key] = case

        raw_suites = payload["suites"]
        if not isinstance(raw_suites, Mapping):
            raise TypeError("suites must be a mapping")
        suites = {
            _coerce_string(suite_name, field_name="suite_name"): BenchmarkSuite.from_dict(
                suite_payload
            )
            for suite_name, suite_payload in raw_suites.items()
        }

        referenced_case_ids = {
            case_id for suite in suites.values() for case_id in suite.case_ids
        }
        if referenced_case_ids - set(cases):
            missing = ", ".join(sorted(referenced_case_ids - set(cases)))
            raise ValueError(f"suites reference unknown case_ids: {missing}")

        return cls(
            version=version,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            cases=cases,
            suites=suites,
        )
