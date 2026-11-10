from fastapi.testclient import TestClient
from skynet_events import InMemoryBus

from catalog_service.app import create_app


def test_create_product_publishes_event():
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        response = client.post("/products", json={"name": "Teclado", "price_cents": 15000, "stock": 5})

    assert response.status_code == 201
    assert [event.event_type for event in bus.published] == ["product.created"]
