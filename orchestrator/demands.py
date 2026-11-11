import json
import re
from dataclasses import dataclass

from orchestrator.config import REPO_ROOT, SERVICES
from orchestrator.platform import run

CYCLES = ("feature", "bug", "guardrail")
PILOT_LABEL = "piloto"
TITLE_WITH_ID = re.compile(r"^\[([A-Z0-9-]+)\]\s*(.+)$")
DEMAND_SECTION = re.compile(r"^## Demanda[ \t]*\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
INTERFACE_SECTION = re.compile(r"^## Interface[ \t]*\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)


@dataclass(frozen=True)
class Demand:
    id: str
    flow: str
    cycle: str
    title: str
    body: str
    issue: int | None = None
    interface: str | None = None


class InvalidIssue(ValueError):
    pass


def _single_label(labels: set[str], prefix: str, allowed: tuple[str, ...]) -> str:
    values = [label.removeprefix(prefix) for label in labels if label.startswith(prefix)]
    if len(values) != 1 or values[0] not in allowed:
        raise InvalidIssue(f"a issue precisa de exatamente um rótulo {prefix}<{'|'.join(allowed)}>")
    return values[0]


def demand_from_issue(issue: dict) -> Demand:
    """O rótulo `piloto` só pode ser aplicado por quem tem acesso de triagem, o que impede rodar issues de terceiros."""
    labels = {label["name"] for label in issue["labels"]}
    if PILOT_LABEL not in labels:
        raise InvalidIssue(f"a issue #{issue['number']} não tem o rótulo '{PILOT_LABEL}'")
    if issue["state"] != "OPEN":
        raise InvalidIssue(f"a issue #{issue['number']} está fechada")

    match = TITLE_WITH_ID.match(issue["title"])
    demand_id, title = (match.group(1), match.group(2)) if match else (f"ISSUE-{issue['number']}", issue["title"])
    section = DEMAND_SECTION.search(issue["body"])
    body = (section.group(1) if section else issue["body"]).strip()
    if not body:
        raise InvalidIssue(f"a issue #{issue['number']} não tem descrição da demanda")

    interface_section = INTERFACE_SECTION.search(issue["body"])
    interface = interface_section.group(1).strip() if interface_section else ""

    return Demand(
        interface=interface or None,
        id=demand_id,
        flow=_single_label(labels, "fluxo:", SERVICES),
        cycle=_single_label(labels, "ciclo:", CYCLES),
        title=title,
        body=body,
        issue=issue["number"],
    )


def fetch_demand(number: int) -> Demand:
    view = run(["gh", "issue", "view", str(number), "--json", "number,title,body,labels,state"], REPO_ROOT)
    return demand_from_issue(json.loads(view.stdout))
