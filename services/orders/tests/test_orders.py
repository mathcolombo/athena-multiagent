from fastapi.testclient import TestClient
from skynet_events import InMemoryBus

from orders_service.app import create_app


def test_unknown_order_returns_404():
    with TestClient(create_app(":memory:", InMemoryBus())) as client:
        response = client.get("/orders/nao-existe")

    assert response.status_code == 404
