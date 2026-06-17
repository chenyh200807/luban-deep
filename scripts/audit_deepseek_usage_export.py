from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import zipfile


DEFAULT_MAX_BYTES = 10 * 1024 * 1024


def _as_max_bytes(value: int | None = None) -> int:
    if value is not None:
        return int(value)
    raw = str(os.getenv("DEEPSEEK_BILLING_EXPORT_MAX_BYTES", "") or "").strip()
    if not raw:
        return DEFAULT_MAX_BYTES
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_BYTES


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _schema_hash(headers: list[str]) -> str:
    return _sha256_bytes(json.dumps(headers, ensure_ascii=False).encode("utf-8"))


def _headers_from_text(handle: io.TextIOBase) -> list[str]:
    reader = csv.reader(handle)
    return [str(value or "").strip() for value in next(reader, [])]


def _assert_under_root(path: Path, root: Path | None) -> None:
    if root is None:
        raise ValueError(f"symlinked billing export is not allowed without a root: {path}")
    path.relative_to(root)


def _resolve_input_path(export_path: Path, billing_export_root: Path | None) -> Path:
    raw_path = Path(export_path).expanduser()
    if not raw_path.exists():
        raise FileNotFoundError(f"DeepSeek usage export path does not exist: {raw_path}")
    resolved = raw_path.resolve()
    if raw_path.is_symlink():
        root = billing_export_root.resolve() if billing_export_root else None
        try:
            _assert_under_root(resolved, root)
        except ValueError as exc:
            raise ValueError(f"rejected symlinked billing export outside root: {raw_path}") from exc
    return resolved


def _check_size(path: Path, max_bytes: int) -> None:
    if path.is_file() and path.stat().st_size > max_bytes:
        raise ValueError(f"DeepSeek usage export exceeds max bytes: {path}")


def _check_zip_entry_size(info: zipfile.ZipInfo, max_bytes: int) -> None:
    if int(info.file_size or 0) > max_bytes:
        raise ValueError(f"DeepSeek usage export entry exceeds max bytes: {info.filename}")


def _assert_export_file_allowed(path: Path, billing_export_root: Path | None) -> Path:
    if not path.is_symlink():
        return path
    resolved = path.resolve()
    try:
        _assert_under_root(resolved, billing_export_root)
    except ValueError as exc:
        raise ValueError(f"rejected symlinked billing export outside root: {path}") from exc
    return resolved


def _file_entry(
    *,
    name: str,
    relative_path: str,
    headers: list[str],
    source_name: str,
    source_sha: str,
) -> dict[str, object]:
    return {
        "name": name,
        "relative_path": relative_path,
        "headers": headers,
        "source_file_name": source_name,
        "source_file_sha256": source_sha,
        "schema_hash": _schema_hash(headers),
    }


def _iter_csv_headers(
    path: Path,
    max_bytes: int,
    billing_export_root: Path | None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if path.is_dir():
        for file in sorted(path.rglob("*.csv")):
            relative_path = file.relative_to(path).as_posix()
            allowed_file = _assert_export_file_allowed(file, billing_export_root)
            _check_size(allowed_file, max_bytes)
            payload = allowed_file.read_bytes()
            with io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8-sig", newline="") as handle:
                rows.append(
                    _file_entry(
                        name=file.name,
                        relative_path=relative_path,
                        headers=_headers_from_text(handle),
                        source_name=file.name,
                        source_sha=_sha256_bytes(payload),
                    )
                )
        return rows

    _check_size(path, max_bytes)
    payload = path.read_bytes()
    source_sha = _sha256_bytes(payload)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for info in sorted(archive.infolist(), key=lambda item: item.filename):
                name = info.filename
                if not name.lower().endswith(".csv"):
                    continue
                _check_zip_entry_size(info, max_bytes)
                with archive.open(name) as raw:
                    text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                    rows.append(
                        _file_entry(
                            name=Path(name).name,
                            relative_path=name,
                            headers=_headers_from_text(text),
                            source_name=path.name,
                            source_sha=source_sha,
                        )
                    )
        return rows

    with io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8-sig", newline="") as handle:
        return [
            _file_entry(
                name=path.name,
                relative_path=path.name,
                headers=_headers_from_text(handle),
                source_name=path.name,
                source_sha=source_sha,
            )
        ]


def audit_export(
    export_path: Path,
    *,
    max_bytes: int | None = None,
    billing_export_root: Path | None = None,
) -> dict[str, object]:
    root = billing_export_root.expanduser().resolve() if billing_export_root else None
    resolved = _resolve_input_path(export_path, root)
    limit = _as_max_bytes(max_bytes)
    return {"files": _iter_csv_headers(resolved, limit, root)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("export_path", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--max-bytes", type=int, default=None)
    args = parser.parse_args()

    payload = audit_export(
        args.export_path,
        max_bytes=args.max_bytes,
        billing_export_root=args.root,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for item in payload["files"]:
            print(f"{item['name']}: {', '.join(item['headers'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
