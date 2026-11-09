import json

from orchestrator.report import summarize, write_report


def write_trace(path, events):
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")


BASE = {"run_id": "r1", "demand": "D", "flow": "catalog", "cycle": "bug"}
AGENT = {**BASE, "event": "agent_finished", "duration_s": 120, "cost_usd": 0.5, "tokens_in": 10, "tokens_cache_read": 5, "tokens_cache_write": 5, "tokens_out": 7, "tool_calls": 3}


def test_summarize_aggregates_metrics(tmp_path):
    path = tmp_path / "r.jsonl"
    write_trace(path, [
        {**BASE, "event": "run_started"},
        AGENT,
        AGENT,
        {**BASE, "event": "gate_decision", "human_minutes": 4.0, "decision": "rejected"},
        {**BASE, "event": "gate_decision", "human_minutes": 1.0, "decision": "approved"},
        {**BASE, "event": "ci_result", "passed": False},
        {**BASE, "event": "coverage", "phase": "before", "percent": 60},
        {**BASE, "event": "guardrail_block", "rule": "secret"},
        {**BASE, "event": "failure", "category": "ci_quebrado"},
        {**BASE, "event": "run_finished", "status": "completed", "wall_s": 3600},
    ])

    summary = summarize(path)

    assert summary.cost_usd == 1.0
    assert summary.agent_min == 4.0
    assert summary.tokens_in == 40
    assert (summary.interventions, summary.rejections, summary.human_min) == (2, 1, 5.0)
    assert summary.ci_failures == 1
    assert summary.coverage_before == 60
    assert summary.block_rules["secret"] == 1
    assert summary.wall_h == 1.0


def test_write_report_ignores_rehearsal_subdir(tmp_path):
    traces = tmp_path / "traces"
    (traces / "rehearsal").mkdir(parents=True)
    write_trace(traces / "a.jsonl", [{**BASE, "event": "run_started"}])
    write_trace(traces / "rehearsal" / "b.jsonl", [{**BASE, "event": "run_started", "demand": "ENSAIO"}])

    message = write_report(traces, tmp_path)

    assert message.startswith("1 execuções")
    assert "ENSAIO" not in (tmp_path / "report.md").read_text()
