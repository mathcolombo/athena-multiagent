import pytest

from orchestrator.checks import parse_tasks
from orchestrator.demands import InvalidIssue, demand_from_issue

BODY = (
    "## Demanda\n\nClientes querem cancelar pedidos.\n\n"
    "## Observação\n\nTexto para humanos.\n\n"
    "## Execução no piloto\n\ncomando\n"
)


def issue(**changes):
    data = {
        "number": 4,
        "title": "[ORD-FEAT-01] cancelamento de pedido",
        "body": BODY,
        "state": "OPEN",
        "labels": [{"name": "piloto"}, {"name": "fluxo:orders"}, {"name": "ciclo:feature"}],
    }
    return data | changes


def test_issue_becomes_demand_with_only_the_demand_section():
    demand = demand_from_issue(issue())

    assert (demand.id, demand.flow, demand.cycle, demand.issue) == ("ORD-FEAT-01", "orders", "feature", 4)
    assert demand.title == "cancelamento de pedido"
    assert demand.body == "Clientes querem cancelar pedidos."


def test_interface_section_is_optional_and_kept_apart():
    without = demand_from_issue(issue())
    with_interface = demand_from_issue(issue(body="## Demanda\n\nTexto.\n\n## Interface\n\nBotão vermelho na linha do pedido.\n"))

    assert without.interface is None
    assert with_interface.interface == "Botão vermelho na linha do pedido."
    assert with_interface.body == "Texto."


def test_issue_without_id_in_title_uses_issue_number():
    demand = demand_from_issue(issue(title="Nova demanda"))

    assert (demand.id, demand.title) == ("ISSUE-4", "Nova demanda")


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"labels": [{"name": "fluxo:orders"}, {"name": "ciclo:feature"}]}, "piloto"),
        ({"state": "CLOSED"}, "fechada"),
        ({"labels": [{"name": "piloto"}, {"name": "ciclo:feature"}]}, "fluxo:"),
        ({"labels": [{"name": "piloto"}, {"name": "fluxo:orders"}, {"name": "ciclo:feature"}, {"name": "ciclo:bug"}]}, "ciclo:"),
        ({"labels": [{"name": "piloto"}, {"name": "fluxo:payments"}, {"name": "ciclo:bug"}]}, "fluxo:"),
    ],
)
def test_invalid_issues_are_refused(changes, message):
    with pytest.raises(InvalidIssue, match=message):
        demand_from_issue(issue(**changes))


def test_parse_tasks_stops_at_next_section():
    story = "## Tasks\n\n### T1: contrato\nCenários: a\n\n### T2: rota\nCenários: b\n\n## Questões em aberto\nnenhuma\n"

    tasks = parse_tasks(story)

    assert [(t.id, t.title) for t in tasks] == [("T1", "contrato"), ("T2", "rota")]
    assert tasks[1].body == "Cenários: b"
