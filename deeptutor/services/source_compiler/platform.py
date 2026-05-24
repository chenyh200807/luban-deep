from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def require_darwin_for_dataless_detection(
    platform_name: str = sys.platform,
    *,
    allow_disabled: bool = False,
) -> None:
    if platform_name != "darwin" and not allow_disabled:
        raise EnvironmentError(
            "dataless detection requires macOS; run with --allow-dataless-scan-disabled only for read-probe-only CI"
        )


def run_with_timeout(args: list[str], *, timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)


def actually_open_and_read(path: Path, head: int = 16 * 1024) -> tuple[bool, int]:
    with path.open("rb") as handle:
        data = handle.read(head)
    return bool(data), len(data)


def _has_fileprovider_dataless_xattr(path: Path) -> bool:
    if not shutil.which("xattr"):
        return False
    result = run_with_timeout(["xattr", "-p", "com.apple.fileprovider.fpfs#PB", str(path)], timeout=5)
    return result.returncode == 0


def detect_dataless(path: Path, *, platform_name: str = sys.platform, allow_disabled: bool = False) -> bool:
    require_darwin_for_dataless_detection(platform_name, allow_disabled=allow_disabled)
    if platform_name != "darwin":
        return False
    if _has_fileprovider_dataless_xattr(path):
        return True
    try:
        stat = path.stat()
    except OSError:
        return True
    return stat.st_size > 0 and getattr(stat, "st_blocks", 1) == 0


class RunDirectoryLock:
    def __init__(self, run_dir: Path, *, force: bool = False) -> None:
        self.run_dir = run_dir
        self.force = force
        self.lock_path = run_dir / ".compile.lock"

    def prepare(self) -> None:
        if self.run_dir.exists() and any(self.run_dir.iterdir()) and not self.force:
            raise FileExistsError(f"Run directory {self.run_dir} is not empty; pass --force to reuse it")
        self.run_dir.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists() and not self.force:
            raise FileExistsError(f"Run directory {self.run_dir} is locked")
        self.lock_path.write_text("locked\n", encoding="utf-8")

    def release(self) -> None:
        self.lock_path.unlink(missing_ok=True)

