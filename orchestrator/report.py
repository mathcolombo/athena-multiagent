import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from orchestrator.config import REPO_ROOT, TRACES_DIR


@dataclass
class RunSummary:
    run_id: str
    demand: str
    flow: str
    cycle: str
    status: str = "incompleta"
    wall_h: float = 0.0
    agent_min: float = 0.0
    human_min: float = 0.0
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    tool_calls: int = 0
    interventions: int = 0
    rejections: int = 0
    edits: int = 0
    ci_failures: int = 0
    coverage_before: int | None = None
    coverage_after: int | None = None
    guardrail_blocks: int = 0
    failures: Counter = field(default_factory=Counter)
    block_rules: Counter = field(default_factory=Counter)


def summarize(path: Path) -> RunSummary | None:
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not events:
        return None
    first = events[0]
    summary = RunSummary(first["run_id"], first["demand"], first["flow"], first["cycle"])
    for event in events:
        kind = event["event"]
        if kind == "agent_finished":
            summary.agent_min += event["duration_s"] / 60
            summary.cost_usd += event["cost_usd"]
            summary.tokens_in += event["tokens_in"] + event["tokens_cache_read"] + event["tokens_cache_write"]
            summary.tokens_out += event["tokens_out"]
            summary.tool_calls += event["tool_calls"]
        elif kind == "gate_decision":
            summary.interventions += 1
            summary.human_min += event["human_minutes"]
            summary.rejections += event["decision"] == "rejected"
            summary.edits += event["decision"] == "edited"
        elif kind == "ci_result":
            summary.ci_failures += not event["passed"]
        elif kind == "coverage":
            setattr(summary, f"coverage_{event['phase']}", event["percent"])
        elif kind == "guardrail_block":
            summary.guardrail_blocks += 1
            summary.block_rules[event["rule"]] += 1
        elif kind == "failure":
            summary.failures[event["category"]] += 1
        elif kind == "run_finished":
            summary.status = event["status"]
            summary.wall_h = event["wall_s"] / 3600
            summary.interventions += event["status"] == "interrupted"
    return summary


def _render(runs: list[RunSummary]) -> str:
    lines = [
        "# Relatório do piloto",
        "",
        "Gerado por `python -m orchestrator report` a partir de `pilot/traces/*.jsonl`. Ensaios ficam fora.",
        "",
        "## Métricas por execução",
        "",
        "| Demanda | Ciclo | Status | Tempo total (h) | Agentes (min) | Humano (min) | Custo (US$) | Intervenções | Reprovações | Edições | Falhas de CI | Cobertura antes → depois |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for run in runs:
        lines.append(
            f"| {run.demand} | {run.cycle} | {run.status} | {run.wall_h:.2f} | {run.agent_min:.1f} | "
            f"{run.human_min:.1f} | {run.cost_usd:.2f} | {run.interventions} | {run.rejections} | {run.edits} | "
            f"{run.ci_failures} | {run.coverage_before}% → {run.coverage_after}% |"
        )

    lines += ["", "## Totais por fluxo", "", "| Fluxo | Execuções | Custo (US$) | Humano (min) | Agentes (min) | Intervenções |", "|---|---:|---:|---:|---:|---:|"]
    for flow in sorted({run.flow for run in runs}):
        group = [run for run in runs if run.flow == flow]
        lines.append(
            f"| {flow} | {len(group)} | {sum(r.cost_usd for r in group):.2f} | {sum(r.human_min for r in group):.1f} | "
            f"{sum(r.agent_min for r in group):.1f} | {sum(r.interventions for r in group)} |"
        )

    failures = sum((run.failures for run in runs), Counter())
    blocks = sum((run.block_rules for run in runs), Counter())
    lines += ["", "## Falhas observadas", "", "| Categoria | Ocorrências |", "|---|---:|"]
    lines += [f"| {name} | {count} |" for name, count in failures.most_common()] or ["| (nenhuma) | 0 |"]
    lines += ["", "## Bloqueios de guarda-corpo", "", "| Regra | Ocorrências |", "|---|---:|"]
    lines += [f"| {name} | {count} |" for name, count in blocks.most_common()] or ["| (nenhum) | 0 |"]
    return "\n".join(lines) + "\n"


def write_report(traces_dir: Path = TRACES_DIR, output_dir: Path = REPO_ROOT / "pilot") -> str:
    runs = [summary for path in sorted(traces_dir.glob("*.jsonl")) if (summary := summarize(path))]
    markdown = output_dir / "report.md"
    markdown.write_text(_render(runs), encoding="utf-8")
    table = output_dir / "report.csv"
    with table.open("w", newline="", encoding="utf-8") as output:
        rows = [{**asdict(run), "failures": dict(run.failures), "block_rules": dict(run.block_rules)} for run in runs]
        fieldnames = list(RunSummary.__dataclass_fields__)
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return f"{len(runs)} execuções consolidadas em {markdown} e {table}"
