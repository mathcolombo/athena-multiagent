import asyncio
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from skynet_events import InMemoryBus, LineItem, OrderCreated, new_event

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


# ---------------------------------------------------------------- CAT-FEAT-01 / T4


def _order_created(items, correlation_id=None):
    payload = OrderCreated(
        order_id="order-1",
        cart_id="cart-1",
        customer_id="cliente-1",
        items=[
            LineItem(product_id=product_id, quantity=quantity, unit_price_cents=1000)
            for product_id, quantity in items
        ],
        total_cents=1000,
    )
    return new_event(payload, "orders", correlation_id or uuid4())


def _types(bus):
    return [event.event_type for event in bus.published]


def test_order_reservation_crossing_threshold_publishes_stock_low_after_reserved():
    """CAT-FEAT-01, cenário "Reserva de pedido cruza o limite"."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        product = _create(client, name="Lampada", stock=5, low_stock_threshold=3).json()
        published_before = len(bus.published)
        order = _order_created([(product["id"], 3)])

        asyncio.run(bus.publish(order))

        new_types = _types(bus)[published_before:]
        assert new_types == ["order.created", "stock.reserved", "stock.low"]
        fetched = client.get(f"/products/{product['id']}").json()
        assert fetched["stock"] == 2
        assert fetched["low_stock"] is True

    low = _low_events(bus)
    assert len(low) == 1
    assert low[0].correlation_id == order.correlation_id
    assert low[0].producer == "catalog"
    assert low[0].payload == {
        "product_id": product["id"],
        "name": "Lampada",
        "stock": 2,
        "threshold": 3,
    }


def test_order_reservation_with_several_products_publishes_one_stock_low_each():
    """CAT-FEAT-01, cenário "Reserva de pedido com vários produtos"."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        first = _create(client, name="Alfa", stock=5, low_stock_threshold=3).json()
        second = _create(client, name="Beta", stock=4, low_stock_threshold=4).json()
        untouched = _create(client, name="Gama", stock=9, low_stock_threshold=3).json()
        order = _order_created([(first["id"], 3), (second["id"], 1), (untouched["id"], 1)])

        asyncio.run(bus.publish(order))

    low = _low_events(bus)
    assert sorted(event.payload["product_id"] for event in low) == sorted(
        [first["id"], second["id"]]
    )
    by_product = {event.payload["product_id"]: event.payload for event in low}
    assert by_product[first["id"]]["stock"] == 2
    assert by_product[second["id"]]["stock"] == 3
    assert all(event.correlation_id == order.correlation_id for event in low)
    assert _types(bus).count("stock.reserved") == 1


def test_order_reservation_same_product_in_two_lines_publishes_single_stock_low():
    """CAT-FEAT-01, "Reserva de pedido com vários produtos": um aviso por produto, não por linha."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        product = _create(client, stock=6, low_stock_threshold=3).json()
        asyncio.run(bus.publish(_order_created([(product["id"], 2), (product["id"], 2)])))

    assert len(_low_events(bus)) == 1
    assert _low_events(bus)[0].payload["stock"] == 2


def test_rejected_reservation_publishes_no_stock_low_and_keeps_stock():
    """CAT-FEAT-01, cenário "Reserva rejeitada não avisa"."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        ok = _create(client, name="Ok", stock=5, low_stock_threshold=3).json()
        short = _create(client, name="Curto", stock=1).json()
        published_before = len(bus.published)

        asyncio.run(bus.publish(_order_created([(ok["id"], 3), (short["id"], 2)])))

        assert _types(bus)[published_before:] == ["order.created", "stock.rejected"]
        assert client.get(f"/products/{ok['id']}").json()["stock"] == 5
        assert client.get(f"/products/{ok['id']}").json()["low_stock"] is False
        assert client.get(f"/products/{short['id']}").json()["stock"] == 1

    assert _low_events(bus) == []


def test_redelivered_order_created_does_not_duplicate_stock_low():
    """CAT-FEAT-01, cenário "Reentrega de order.created não duplica aviso"."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        product = _create(client, stock=5, low_stock_threshold=3).json()
        order = _order_created([(product["id"], 3)])
        asyncio.run(bus.publish(order))
        published_before = len(bus.published)

        asyncio.run(bus.deliver(order))

        assert len(bus.published) == published_before
        assert client.get(f"/products/{product['id']}").json()["stock"] == 2

    assert len(_low_events(bus)) == 1


def test_order_reservation_while_already_low_does_not_publish_again():
    """CAT-FEAT-01, cenário "Sem repetição enquanto continua baixo" (reserva)."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        product = _create(client, stock=2, low_stock_threshold=3).json()
        assert len(_low_events(bus)) == 1

        asyncio.run(bus.publish(_order_created([(product["id"], 1)])))

        assert client.get(f"/products/{product['id']}").json()["stock"] == 1
        assert "stock.reserved" in _types(bus)

    assert len(_low_events(bus)) == 1


def test_order_reservation_without_threshold_never_publishes_stock_low():
    """CAT-FEAT-01, cenário "Produto sem limite nunca avisa" (reserva)."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        product = _create(client, stock=3).json()
        asyncio.run(bus.publish(_order_created([(product["id"], 3)])))

        assert client.get(f"/products/{product['id']}").json()["stock"] == 0
        assert client.get(f"/products/{product['id']}").json()["low_stock"] is False

    assert _low_events(bus) == []
    assert "stock.reserved" in _types(bus)


def test_reservation_not_crossing_threshold_does_not_publish():
    """CAT-FEAT-01, T4: reserva que deixa estoque igual ao limite não avisa."""
    bus = InMemoryBus()
    with TestClient(create_app(":memory:", bus)) as client:
        product = _create(client, stock=5, low_stock_threshold=3).json()
        asyncio.run(bus.publish(_order_created([(product["id"], 2)])))

    assert _low_events(bus) == []


def test_reserve_stock_db_reports_crossed_products_only_when_confirmed():
    """CAT-FEAT-01, T4: `reserve_stock` devolve os produtos que cruzaram o limite, ou None se rejeitada."""
    db = CatalogDb(":memory:")
    crossing = db.create_product("Cruza", 100, 5, 3)
    plain = db.create_product("Sem", 100, 5)

    crossed = db.reserve_stock([(crossing["id"], 3), (plain["id"], 5)])
    assert [row["id"] for row in crossed] == [crossing["id"]]
    assert crossed[0]["stock"] == 2

    assert db.reserve_stock([(crossing["id"], 1), (plain["id"], 1)]) is None
    assert db.get_product(crossing["id"])["stock"] == 2
    assert db.reserve_stock([(crossing["id"], 1)]) == []
