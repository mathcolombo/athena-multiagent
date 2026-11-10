from fastapi.testclient import TestClient
from skynet_events import InMemoryBus

from catalog_service.app import create_app


def test_create_product_publishes_event():
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        response = client.post("/products", json={"name": "Teclado", "price_cents": 15000, "stock": 5})

    assert response.status_code == 201
    assert [event.event_type for event in bus.published] == ["product.created"]


def test_patch_price_publishes_price_changed_with_old_and_new_price():
    """CAT-BUG-01 (RN-02): alterar o preço pelo PATCH deve publicar
    product.price_changed, para que o carrinho atualize seu snapshot.
    Sem a correção, o preço antigo era lido após o update e o evento
    nunca era publicado (antigo == novo)."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        created = client.post("/products", json={"name": "Mouse", "price_cents": 5000, "stock": 3}).json()
        response = client.patch(f"/products/{created['id']}", json={"price_cents": 7500})

        assert response.status_code == 200
        assert client.get(f"/products/{created['id']}").json()["price_cents"] == 7500

    changed = [event for event in bus.published if event.event_type == "product.price_changed"]
    assert len(changed) == 1
    assert changed[0].payload == {
        "product_id": created["id"],
        "old_price_cents": 5000,
        "new_price_cents": 7500,
    }


def test_patch_without_price_change_does_not_publish_price_changed():
    """Complemento CAT-BUG-01: PATCH que não muda o preço não gera evento."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        created = client.post("/products", json={"name": "Mouse", "price_cents": 5000, "stock": 3}).json()
        client.patch(f"/products/{created['id']}", json={"name": "Mouse Gamer"})
        client.patch(f"/products/{created['id']}", json={"price_cents": 5000})

    assert [event.event_type for event in bus.published] == ["product.created"]
