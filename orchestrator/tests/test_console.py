import io
import json

from orchestrator.console import ConsoleLog
from orchestrator.tracing import Trace


def test_trace_events_are_shown_in_terminal(tmp_path):
    output = io.StringIO()
    trace = Trace(tmp_path / "t.jsonl", "r1", listener=ConsoleLog(output), demand="D", flow="catalog", cycle="bug")

    trace.emit("phase", name="Implementação")
    trace.emit("tool_call", agent="codigo", tool="Bash", input={"command": "pytest -q"}, allowed=True)
    trace.emit("guardrail_block", agent="deploy", tool="Bash", input={"command": "cat .env"}, rule="secret")
    trace.emit(
        "agent_finished", agent="codigo", subtype="success", is_error=False, duration_s=12.0,
        num_turns=4, tool_calls=3, cost_usd=0.05,
    )

    lines = output.getvalue().splitlines()
    assert "── Implementação" in lines[0]
    assert "[codigo] → Bash pytest -q" in lines[1]
    assert "bloqueado [secret]: Bash cat .env" in lines[2]
    assert "US$ 0.050" in lines[3]


def test_silent_events_are_not_printed(tmp_path):
    output = io.StringIO()
    trace = Trace(tmp_path / "t.jsonl", "r1", listener=ConsoleLog(output))

    trace.emit("tool_call", agent="codigo", tool="Read", input={"file_path": ".env"}, allowed=False)

    assert output.getvalue() == ""
