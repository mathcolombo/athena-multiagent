import os
import time
from dataclasses import dataclass
from typing import Protocol

FAILURE_CATEGORIES = (
    "alucinacao",
    "especificacao_mal_interpretada",
    "teste_tautologico",
    "qualidade_codigo",
    "seguranca",
    "outra",
)


@dataclass(frozen=True)
class GateDecision:
    decision: str  # approved | rejected | edited
    comment: str
    approver: str
    wall_s: float
    human_minutes: float
    failure_category: str | None = None
    rework_target: str = "ambos"


class Gates(Protocol):
    def decide(self, gate: str, summary: str, can_edit: bool = True) -> GateDecision: ...

    def wait(self, message: str) -> None: ...


class TerminalGates:
    """Aprovação humana real; o tempo informado alimenta a métrica de esforço."""

    def __init__(self, operator: str | None = None) -> None:
        self.operator = operator or os.environ.get("PILOT_OPERATOR", "")

    def decide(self, gate: str, summary: str, can_edit: bool = True) -> GateDecision:
        started = time.monotonic()
        print(f"\n{'=' * 72}\nGATE {gate}\n{'-' * 72}\n{summary}\n{'=' * 72}")
        options = "[a]provar, [r]eprovar" + (", [e]ditar manualmente" if can_edit else "")
        valid = {"a": "approved", "r": "rejected"} | ({"e": "edited"} if can_edit else {})
        choice = ""
        while choice not in valid:
            choice = input(f"{options}: ").strip().lower()[:1]
        decision = valid[choice]

        comment, category, target = "", None, "ambos"
        if decision == "rejected":
            comment = input("Motivo da reprovação (enviado ao agente): ").strip()
            for index, name in enumerate(FAILURE_CATEGORIES, 1):
                print(f"  {index}. {name}")
            answer = input("Categoria da falha [6]: ").strip() or "6"
            category = FAILURE_CATEGORIES[int(answer) - 1] if answer.isdigit() and 0 < int(answer) <= 6 else "outra"
            target = {"1": "codigo", "2": "testes"}.get(
                input("Retrabalho para: 1) código 2) testes 3) ambos [3]: ").strip(), "ambos"
            )
        elif decision == "edited":
            comment = input("Edite os arquivos no worktree, descreva o ajuste e pressione Enter: ").strip()

        approver = ""
        while not approver:
            approver = input(f"Aprovador (nome e papel) [{self.operator}]: ").strip() or self.operator
        self.operator = approver
        wall = time.monotonic() - started
        answer = input(f"Minutos de trabalho humano [{wall / 60:.1f}]: ").strip().replace(",", ".")
        return GateDecision(decision, comment, approver, wall, float(answer) if answer else wall / 60, category, target)

    def wait(self, message: str) -> None:
        input(message)


class ScriptedGates:
    """Somente para ensaios e testes: as execuções geradas ficam fora do relatório oficial."""

    def __init__(self, decisions: list[GateDecision] | None = None) -> None:
        self.decisions = list(decisions or [])

    def decide(self, gate: str, summary: str, can_edit: bool = True) -> GateDecision:
        if self.decisions:
            return self.decisions.pop(0)
        return GateDecision("approved", "aprovação automática de ensaio", "ensaio", 0.0, 0.0)

    def wait(self, message: str) -> None:
        pass
