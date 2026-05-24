from __future__ import annotations

from .metadata import with_compiler_metadata


def build_taxonomy_index(records: list[dict], *, run_id: str, source_path: str, compiled_at: str) -> list[dict]:
    rows: list[dict] = []
    for record in records:
        node_code = str(record.get("node_code") or record.get("code") or "").strip()
        if not node_code:
            continue
        path_names = record.get("path_names") or record.get("path") or []
        if isinstance(path_names, str):
            path_names = [part for part in path_names.split("/") if part]
        payload = {
            "node_code": node_code,
            "name": record.get("name") or record.get("title") or node_code,
            "path_names": path_names,
            "raw": record,
        }
        rows.append(with_compiler_metadata(payload, run_id=run_id, source_path=source_path, compiled_at=compiled_at))
    return rows


class TaxonomyIndex:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def lookup_node_by_code(self, node_code: str) -> dict | None:
        for row in self.rows:
            if row.get("node_code") == node_code:
                return row
        return None

    def lookup_node_by_path(self, path_names: list[str]) -> dict | None:
        for row in self.rows:
            if row.get("path_names") == path_names:
                return row
        return None

    def lookup_node_by_name(self, name: str) -> dict | None:
        matches = [row for row in self.rows if row.get("name") == name]
        if len(matches) > 1:
            raise ValueError(f"ambiguous taxonomy name: {name}")
        return matches[0] if matches else None

