from orchestrator.config import DEMANDS_DIR
from orchestrator.demands import find_demand, parse_demand


def test_every_pilot_demand_is_linked_to_an_issue():
    demands = [parse_demand(path) for path in sorted(DEMANDS_DIR.glob("*.md"))]

    assert len(demands) == 5
    assert all(demand.issue for demand in demands)
    assert len({demand.issue for demand in demands}) == 5


def test_find_demand_by_flow_and_cycle():
    demand = find_demand("orders", "bug")

    assert (demand.id, demand.issue) == ("ORD-BUG-01", 5)
