from dataclasses import dataclass
from pathlib import Path

from orchestrator.config import DEMANDS_DIR


@dataclass(frozen=True)
class Demand:
    id: str
    flow: str
    cycle: str
    title: str
    body: str
    issue: int | None = None


def parse_demand(path: Path) -> Demand:
    _, header, body = path.read_text(encoding="utf-8").split("---\n", 2)
    fields = dict(line.split(": ", 1) for line in header.strip().splitlines())
    issue = int(fields["issue"]) if "issue" in fields else None
    return Demand(fields["id"], fields["flow"], fields["cycle"], fields["title"], body.strip(), issue)


def find_demand(flow: str, cycle: str, directory: Path = DEMANDS_DIR) -> Demand:
    matches = [
        demand for demand in map(parse_demand, sorted(directory.glob("*.md")))
        if demand.flow == flow and demand.cycle == cycle
    ]
    if len(matches) != 1:
        raise SystemExit(f"Esperada 1 demanda para {flow}/{cycle}, encontradas {len(matches)}")
    return matches[0]
