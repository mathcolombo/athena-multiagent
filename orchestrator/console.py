import sys
from datetime import datetime
from typing import Any, TextIO

COLORS = {"dim": "2", "bold": "1", "red": "31", "green": "32", "yellow": "33", "blue": "34", "magenta": "35", "cyan": "36"}
AGENT_COLORS = {"requisitos": "magenta", "codigo": "blue", "testes": "cyan", "deploy": "yellow"}
MAX_WIDTH = 160


def one_line(text: Any, width: int = MAX_WIDTH) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= width else flat[: width - 1] + "…"


def tool_summary(tool: str, tool_input: dict) -> str:
    for key in ("command", "file_path", "pattern", "path"):
        if tool_input.get(key):
            return f"{tool} {tool_input[key]}"
    return tool


class ConsoleLog:
    """Mostra no terminal, em tempo real, o que o supervisor e os agentes estão fazendo."""

    def __init__(self, stream: TextIO = sys.stdout) -> None:
        self.stream = stream
        self.color = stream.isatty()

    def paint(self, text: str, color: str) -> str:
        return f"\033[{COLORS[color]}m{text}\033[0m" if self.color else text

    def agent(self, name: str) -> str:
        return self.paint(f"[{name}]", AGENT_COLORS.get(name, "bold"))

    def __call__(self, record: dict) -> None:
        line = self.format(record)
        if line:
            clock = self.paint(datetime.now().strftime("%H:%M:%S"), "dim")
            print(f"{clock} {line}", file=self.stream, flush=True)

    def format(self, r: dict) -> str | None:
        event = r["event"]
        agent = self.agent(r["agent"]) if "agent" in r else ""
        ok, fail = self.paint("✔", "green"), self.paint("✖", "red")
        match event:
            case "run_started":
                return self.paint(f"▶ {r['run_id']} · {r['demand']} ({r['flow']}/{r['cycle']}) · modelo {r['model']} · {r['platform']}", "bold")
            case "phase":
                return self.paint(f"── {r['name']}", "bold")
            case "tasks_planned":
                listed = " · ".join(f"{task['id']} {task['title']}" for task in r["tasks"])
                return self.paint(f"   {len(r['tasks'])} tasks planejadas: {listed}", "bold")
            case "task_started":
                return self.paint(f"▸ task {r['task']} ({r['position']}/{r['total']}): {r['title']}", "bold")
            case "task_finished":
                return f"   {ok} task {r['task']} commitada"
            case "coverage":
                percent = "indisponível" if r["percent"] is None else f"{r['percent']}%"
                return f"   cobertura {'antes' if r['phase'] == 'before' else 'depois'}: {percent}"
            case "agent_started":
                return f"{agent} iniciado"
            case "agent_message":
                return f"{agent} {self.paint(one_line(r['text']), 'dim')}"
            case "tool_call" if r["allowed"]:
                return f"{agent} → {one_line(tool_summary(r['tool'], r['input']))}"
            case "guardrail_block":
                return f"{agent} {fail} bloqueado [{r['rule']}]: {one_line(tool_summary(r['tool'], r['input']))}"
            case "agent_finished":
                mark = fail if r["is_error"] else ok
                return (
                    f"{agent} {mark} {r['subtype']} em {r['duration_s']:.0f}s · {r['num_turns']} turnos · "
                    f"{r['tool_calls']} ferramentas · US$ {r['cost_usd']:.3f}"
                )
            case "quality_check":
                return f"   verificações de qualidade: {ok if r['passed'] else fail + ' ' + '; '.join(r['problems'])}"
            case "regression_check":
                return f"   teste de regressão falha sem a correção: {ok if r['failed_on_base'] else fail}"
            case "suite_result":
                return f"   suíte de testes (tentativa {r['attempt']}): {ok + ' verde' if r['passed'] else fail + ' falhou'}"
            case "issue_commented":
                return f"   {ok} decisão do {r['gate']} registrada na issue #{r['issue']}"
            case "pr_opened":
                return f"   PR aberto: {r['url']}"
            case "ci_result":
                return f"   CI tentativa {r['attempt']}: {ok + ' verde' if r['passed'] else fail + ' falhou'}"
            case "merge_pending":
                return self.paint(f"   aguardando merge do PR #{r['number']}", "yellow")
            case "pr_merged":
                return f"   {ok} PR #{r['number']} mesclado"
            case "gate_decision":
                return self.paint(f"   gate {r['gate']}: {r['decision']} por {r['approver']} ({r['human_minutes']:.1f} min)", "bold")
            case "health_check":
                return f"   health check independente: {ok + ' OK' if r['healthy'] else fail + ' falhou'}"
            case "release":
                return f"   {ok} virada autorizada: {r['tag']}"
            case "rollback":
                return self.paint(f"   rollback: {r['reason']}", "red")
            case "failure":
                return self.paint(f"   falha [{r['category']}] {one_line(r['description'])}", "red")
            case "guardrail_result":
                leaked = fail + " canário vazou" if r["canary_leaked"] else ok + " canário protegido"
                return f"   bloqueios: {', '.join(r['blocks']) or 'nenhum'} · {leaked}"
            case "run_finished":
                color = "green" if r["status"] == "completed" else "red"
                return self.paint(f"■ {r['status']} em {r['wall_s'] / 60:.1f} min {r['reason']}", color)
        return None
