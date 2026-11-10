from fastapi.testclient import TestClient
from skynet_events import InMemoryBus

from cart_service.app import create_app


def test_create_cart_starts_empty():
    with TestClient(create_app(":memory:", InMemoryBus())) as client:
        response = client.post("/carts", json={"customer_id": "c1"})

    assert response.status_code == 201
    assert response.json()["items"] == []
