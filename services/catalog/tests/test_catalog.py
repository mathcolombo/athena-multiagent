import sqlite3

import pytest
from fastapi.testclient import TestClient
from skynet_events import InMemoryBus

from catalog_service.app import create_app
from catalog_service.db import CatalogDb


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


# ---------------------------------------------------------------- CAT-FEAT-01 / T2


def _create(client, **overrides):
    body = {"name": "Cabo", "price_cents": 1000, "stock": 10}
    body.update(overrides)
    return client.post("/products", json=body)


def test_create_product_with_threshold():
    """CAT-FEAT-01, cenário "Cadastrar produto com limite"."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        response = _create(client, stock=10, low_stock_threshold=3)
        assert response.status_code == 201
        body = response.json()
        assert body["low_stock_threshold"] == 3
        assert body["low_stock"] is False
        assert client.get(f"/products/{body['id']}").json()["low_stock_threshold"] == 3

    assert "stock.low" not in [event.event_type for event in bus.published]


def test_create_product_without_threshold():
    """CAT-FEAT-01, cenário "Cadastrar produto sem limite"."""
    with TestClient(create_app(":memory:", InMemoryBus())) as client:
        body = _create(client).json()
        assert body["low_stock_threshold"] is None
        assert body["low_stock"] is False
        assert client.get(f"/products/{body['id']}").json()["low_stock_threshold"] is None


def test_patch_without_threshold_preserves_it():
    """CAT-FEAT-01, cenário "Alteração sem mencionar o limite preserva o limite"."""
    with TestClient(create_app(":memory:", InMemoryBus())) as client:
        product = _create(client, low_stock_threshold=3).json()
        response = client.patch(f"/products/{product['id']}", json={"price_cents": 2000})

        assert response.status_code == 200
        assert response.json()["low_stock_threshold"] == 3
        fetched = client.get(f"/products/{product['id']}").json()
        assert fetched["low_stock_threshold"] == 3
        assert fetched["price_cents"] == 2000


def test_patch_null_threshold_removes_it():
    """CAT-FEAT-01, cenário "Remover o limite"."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        product = _create(client, stock=2, low_stock_threshold=3).json()
        published_before = len(bus.published)
        response = client.patch(f"/products/{product['id']}", json={"low_stock_threshold": None})

        assert response.status_code == 200
        assert response.json()["low_stock_threshold"] is None
        fetched = client.get(f"/products/{product['id']}").json()
        assert fetched["low_stock_threshold"] is None
        assert fetched["low_stock"] is False

    assert len(bus.published) == published_before


def test_patch_sets_and_changes_threshold():
    """CAT-FEAT-01, cenário "Remover o limite" (complemento): limite informado é gravado."""
    with TestClient(create_app(":memory:", InMemoryBus())) as client:
        product = _create(client, stock=10).json()
        response = client.patch(f"/products/{product['id']}", json={"low_stock_threshold": 4})
        assert response.json()["low_stock_threshold"] == 4
        assert client.get(f"/products/{product['id']}").json()["low_stock_threshold"] == 4


def test_create_with_negative_threshold_is_rejected():
    """CAT-FEAT-01, cenário "Limite inválido" (cadastro)."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        response = _create(client, low_stock_threshold=-1)
        assert response.status_code == 422
        assert client.get("/products").json() == []

    assert bus.published == []


def test_patch_with_negative_threshold_is_rejected_and_changes_nothing():
    """CAT-FEAT-01, cenário "Limite inválido" (alteração)."""
    with TestClient(create_app(":memory:", InMemoryBus())) as client:
        product = _create(client, low_stock_threshold=3).json()
        response = client.patch(
            f"/products/{product['id']}", json={"low_stock_threshold": -5, "price_cents": 1}
        )
        assert response.status_code == 422
        assert client.get(f"/products/{product['id']}").json() == product


def test_create_with_non_integer_threshold_is_rejected():
    """CAT-FEAT-01, cenário "Limite inválido": valor não inteiro."""
    with TestClient(create_app(":memory:", InMemoryBus())) as client:
        assert _create(client, low_stock_threshold="muito").status_code == 422
        assert _create(client, low_stock_threshold=1.5).status_code == 422


def test_zero_threshold_is_valid_and_never_low():
    """CAT-FEAT-01, "Limite inválido": zero é aceito (inteiro >= 0); estoque 0 não é menor que 0."""
    with TestClient(create_app(":memory:", InMemoryBus())) as client:
        body = _create(client, stock=0, low_stock_threshold=0).json()
        assert body["low_stock_threshold"] == 0
        assert body["low_stock"] is False


def test_query_reports_threshold_and_low_stock_for_list_and_detail():
    """CAT-FEAT-01, cenário "Consulta informa limite e situação"."""
    with TestClient(create_app(":memory:", InMemoryBus())) as client:
        low = _create(client, name="A-baixo", stock=2, low_stock_threshold=5).json()
        equal = _create(client, name="B-igual", stock=5, low_stock_threshold=5).json()
        above = _create(client, name="C-acima", stock=9, low_stock_threshold=5).json()
        none = _create(client, name="D-sem", stock=0).json()

        listed = {p["id"]: p for p in client.get("/products").json()}
        expected = {
            low["id"]: (5, True),
            equal["id"]: (5, False),
            above["id"]: (5, False),
            none["id"]: (None, False),
        }
        for product_id, (threshold, is_low) in expected.items():
            for view in (listed[product_id], client.get(f"/products/{product_id}").json()):
                assert view["low_stock_threshold"] == threshold
                assert view["low_stock"] is is_low


def test_low_stock_reflects_threshold_patch():
    """CAT-FEAT-01, "Consulta informa limite e situação": low_stock acompanha mudança do limite."""
    with TestClient(create_app(":memory:", InMemoryBus())) as client:
        product = _create(client, stock=5).json()
        client.patch(f"/products/{product['id']}", json={"low_stock_threshold": 8})
        assert client.get(f"/products/{product['id']}").json()["low_stock"] is True
        client.patch(f"/products/{product['id']}", json={"low_stock_threshold": 5})
        assert client.get(f"/products/{product['id']}").json()["low_stock"] is False


def test_existing_database_without_column_is_migrated(tmp_path):
    """CAT-FEAT-01, T2: migração de banco existente sem a coluna `low_stock_threshold`."""
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.executescript(
        """
        CREATE TABLE products (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
            stock INTEGER NOT NULL CHECK (stock >= 0)
        );
        CREATE TABLE processed_events (event_id TEXT PRIMARY KEY);
        INSERT INTO products VALUES ('legacy-1', 'Antigo', 100, 4);
        """
    )
    old.commit()
    old.close()

    with TestClient(create_app(path, InMemoryBus())) as client:
        legacy = client.get("/products/legacy-1").json()
        assert legacy["low_stock_threshold"] is None
        assert legacy["low_stock"] is False

        client.patch("/products/legacy-1", json={"low_stock_threshold": 9})
        migrated = client.get("/products/legacy-1").json()
        assert migrated["low_stock_threshold"] == 9
        assert migrated["low_stock"] is True


def test_database_rejects_negative_threshold_directly():
    """CAT-FEAT-01, T2: a coluna tem CHECK (>= 0), independentemente da validação da API."""
    db = CatalogDb(":memory:")
    with pytest.raises(sqlite3.IntegrityError):
        db.create_product("X", 1, 1, -1)


# ---------------------------------------------------------------- CAT-FEAT-01 / T3


def _low_events(bus):
    return [event for event in bus.published if event.event_type == "stock.low"]


def test_create_product_already_below_threshold_publishes_stock_low():
    """CAT-FEAT-01, cenário "Cadastrar produto já abaixo do limite"."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        product = _create(client, name="Pilha", stock=2, low_stock_threshold=5).json()

    assert product["low_stock"] is True
    low = _low_events(bus)
    assert len(low) == 1
    assert low[0].producer == "catalog"
    assert low[0].payload == {
        "product_id": product["id"],
        "name": "Pilha",
        "stock": 2,
        "threshold": 5,
    }


def test_manual_stock_change_crossing_threshold_publishes_stock_low():
    """CAT-FEAT-01, cenário "Alteração manual de estoque cruza o limite"."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        product = _create(client, name="Fita", stock=5, low_stock_threshold=3).json()
        assert _low_events(bus) == []
        response = client.patch(f"/products/{product['id']}", json={"stock": 2})
        assert response.status_code == 200
        assert client.get(f"/products/{product['id']}").json()["low_stock"] is True

    low = _low_events(bus)
    assert len(low) == 1
    assert low[0].payload == {
        "product_id": product["id"],
        "name": "Fita",
        "stock": 2,
        "threshold": 3,
    }


def test_stock_equal_to_threshold_is_not_low():
    """CAT-FEAT-01, cenário "Estoque igual ao limite não é baixo"."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        product = _create(client, stock=5, low_stock_threshold=3).json()
        client.patch(f"/products/{product['id']}", json={"stock": 3})
        assert client.get(f"/products/{product['id']}").json()["low_stock"] is False

    assert _low_events(bus) == []


def test_no_repeated_stock_low_while_still_low():
    """CAT-FEAT-01, cenário "Sem repetição enquanto continua baixo" (alteração manual)."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        product = _create(client, stock=5, low_stock_threshold=3).json()
        client.patch(f"/products/{product['id']}", json={"stock": 2})
        client.patch(f"/products/{product['id']}", json={"stock": 1})
        client.patch(f"/products/{product['id']}", json={"stock": 0})
        client.patch(f"/products/{product['id']}", json={"price_cents": 1})

    assert len(_low_events(bus)) == 1


def test_replenish_then_new_crossing_publishes_again():
    """CAT-FEAT-01, cenário "Reposição e novo cruzamento"."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        product = _create(client, stock=2, low_stock_threshold=3).json()
        assert len(_low_events(bus)) == 1

        client.patch(f"/products/{product['id']}", json={"stock": 3})
        assert client.get(f"/products/{product['id']}").json()["low_stock"] is False
        assert len(_low_events(bus)) == 1

        client.patch(f"/products/{product['id']}", json={"stock": 1})
        assert client.get(f"/products/{product['id']}").json()["low_stock"] is True

    low = _low_events(bus)
    assert len(low) == 2
    assert low[1].payload["stock"] == 1
    assert low[1].payload["threshold"] == 3


def test_replenish_above_threshold_then_cross_again():
    """CAT-FEAT-01, "Reposição e novo cruzamento": reposição acima do limite."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        product = _create(client, stock=1, low_stock_threshold=3).json()
        client.patch(f"/products/{product['id']}", json={"stock": 20})
        client.patch(f"/products/{product['id']}", json={"stock": 2})

    assert len(_low_events(bus)) == 2


def test_setting_threshold_above_current_stock_publishes_stock_low():
    """CAT-FEAT-01, cenário "Configurar limite acima do estoque atual"."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        product = _create(client, name="Bateria", stock=5).json()
        assert _low_events(bus) == []
        client.patch(f"/products/{product['id']}", json={"low_stock_threshold": 8})
        assert client.get(f"/products/{product['id']}").json()["low_stock"] is True

    low = _low_events(bus)
    assert len(low) == 1
    assert low[0].payload == {
        "product_id": product["id"],
        "name": "Bateria",
        "stock": 5,
        "threshold": 8,
    }


def test_raising_threshold_when_already_low_does_not_publish_again():
    """CAT-FEAT-01, cenário "Aumentar o limite com produto já baixo"."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        product = _create(client, stock=2, low_stock_threshold=3).json()
        assert len(_low_events(bus)) == 1
        client.patch(f"/products/{product['id']}", json={"low_stock_threshold": 6})
        assert client.get(f"/products/{product['id']}").json()["low_stock"] is True

    assert len(_low_events(bus)) == 1


def test_lowering_threshold_takes_product_out_of_low_without_event():
    """CAT-FEAT-01, cenário "Reduzir o limite tira o produto de estoque baixo"."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        product = _create(client, stock=2, low_stock_threshold=3).json()
        published_before = len(bus.published)
        client.patch(f"/products/{product['id']}", json={"low_stock_threshold": 2})
        assert client.get(f"/products/{product['id']}").json()["low_stock"] is False

    assert len(bus.published) == published_before


def test_product_without_threshold_never_publishes_stock_low_on_manual_change():
    """CAT-FEAT-01, cenário "Produto sem limite nunca avisa" (alteração manual)."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        product = _create(client, stock=5).json()
        client.patch(f"/products/{product['id']}", json={"stock": 1})
        client.patch(f"/products/{product['id']}", json={"stock": 0})
        assert client.get(f"/products/{product['id']}").json()["low_stock"] is False

    assert _low_events(bus) == []


def test_removing_threshold_then_stock_drop_does_not_publish():
    """CAT-FEAT-01, "Produto sem limite nunca avisa": limite removido deixa de avisar."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        product = _create(client, stock=5, low_stock_threshold=3).json()
        client.patch(f"/products/{product['id']}", json={"low_stock_threshold": None})
        client.patch(f"/products/{product['id']}", json={"stock": 0})

    assert _low_events(bus) == []
