from __future__ import annotations

import csv
import subprocess
from io import StringIO


PSQL_BASE_ARGS = [
    "psql",
    "-X",
    "-v",
    "ON_ERROR_STOP=1",
    "-P",
    "pager=off",
    "--csv",
]


class PsqlRunner:
    def __init__(self, db_url: str, *, timeout: int = 30) -> None:
        self.db_url = db_url
        self.timeout = timeout

    def run_csv(self, sql: str) -> list[dict[str, str]]:
        result = subprocess.run(
            [*PSQL_BASE_ARGS, "-d", self.db_url, "-c", sql],
            text=True,
            capture_output=True,
            timeout=self.timeout,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return list(csv.DictReader(StringIO(result.stdout)))

    def scalar(self, sql: str) -> str:
        rows = self.run_csv(sql)
        if not rows:
            return ""
        return next(iter(rows[0].values())) or ""


def assert_target_database_is_main(psql_runner) -> None:
    regclass = psql_runner.scalar("SELECT to_regclass('public.questions_bank')")
    if regclass not in {"questions_bank", "public.questions_bank"}:
        raise RuntimeError("Target database is not DeepTutor main: missing public.questions_bank")
    count = int(psql_runner.scalar("SELECT count(*) FROM public.questions_bank"))
    if count < 1000:
        raise RuntimeError(f"Target database is suspicious: questions_bank count={count}")

