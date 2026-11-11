import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SECRET_PATTERN = re.compile(r"(sk-ant-[\w-]+|gh[pousr]_\w+|github_pat_\w+)")
MAX_TEXT = 2000


def sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return SECRET_PATTERN.sub("[REDACTED]", value)[:MAX_TEXT]
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [sanitize(item) for item in value]
    return value


class Trace:
    """Log de auditoria append-only de uma execução, um evento JSON por linha."""

    def __init__(
        self,
        path: Path,
        run_id: str,
        listener: Callable[[dict], None] | None = None,
        **common: Any,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.run_id = run_id
        self.listener = listener
        self.common = common

    def emit(self, event: str, **fields: Any) -> None:
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "run_id": self.run_id,
            "event": event,
            **self.common,
            **sanitize(fields),
        }
        with self.path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
        if self.listener is not None:
            self.listener(record)
