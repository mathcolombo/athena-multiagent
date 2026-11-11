from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from skynet_events import (
    EventEnvelope,
    InMemoryBus,
    ProductPriceChanged,
    StockLow,
    StockReserved,
    decode,
    new_event,
)


def test_decode_round_trip():
    event = new_event(
        ProductPriceChanged(product_id="p1", old_price_cents=100, new_price_cents=90), "catalog"
    )

    assert event.event_type == "product.price_changed"
    assert decode(event, ProductPriceChanged).new_price_cents == 90


def test_decode_rejects_wrong_type():
    event = new_event(StockReserved(order_id="o1"), "catalog")

    with pytest.raises(ValueError):
        decode(event, ProductPriceChanged)


def test_stock_low_contract_metadata_and_export():
    """CAT-FEAT-01 T1: contrato StockLow (stock.low, versão 1) exportado."""
    import skynet_events

    assert "StockLow" in skynet_events.__all__
    assert skynet_events.StockLow.EVENT_TYPE == "stock.low"
    assert skynet_events.StockLow.VERSION == 1


def test_stock_low_envelope_round_trip():
    """CAT-FEAT-01 T1: StockLow é codificado no envelope e decodificado."""
    correlation_id = uuid4()
    event = new_event(
        StockLow(product_id="p1", name="Caneta", stock=2, threshold=5),
        "catalog",
        correlation_id,
    )

    assert event.event_type == "stock.low"
    assert event.version == 1
    assert event.producer == "catalog"
    assert event.correlation_id == correlation_id
    assert event.payload == {"product_id": "p1", "name": "Caneta", "stock": 2, "threshold": 5}

    decoded = decode(event, StockLow)
    assert decoded.product_id == "p1"
    assert decoded.name == "Caneta"
    assert decoded.stock == 2
    assert decoded.threshold == 5


def test_stock_low_survives_json_serialization():
    """CAT-FEAT-01 T1: envelope com StockLow sobrevive a ida e volta em JSON."""
    event = new_event(StockLow(product_id="p1", name="Caneta", stock=0, threshold=3), "catalog")

    restored = EventEnvelope.model_validate_json(event.model_dump_json())

    assert restored == event
    assert decode(restored, StockLow).threshold == 3


def test_stock_low_requires_all_fields():
    """CAT-FEAT-01 T1: campos do contrato são obrigatórios."""
    with pytest.raises(ValidationError):
        StockLow.model_validate({"product_id": "p1", "name": "Caneta", "stock": 1})


def test_decode_stock_low_rejects_other_type():
    """CAT-FEAT-01 T1: decode de StockLow rejeita outro tipo de evento."""
    event = new_event(StockReserved(order_id="o1"), "catalog")

    with pytest.raises(ValueError):
        decode(event, StockLow)


async def test_in_memory_bus_delivers_stock_low_to_subscriber():
    """CAT-FEAT-01 T1: barramento em memória entrega stock.low a assinantes."""
    bus = InMemoryBus()
    received = []

    async def handler(event):
        received.append(event)

    await bus.subscribe("purchasing", ["stock.low"], handler)
    await bus.publish(new_event(StockLow(product_id="p1", name="Caneta", stock=1, threshold=4), "catalog"))

    assert [decode(e, StockLow).stock for e in received] == [1]
    assert [e.event_type for e in bus.published] == ["stock.low"]


def test_rn07_in_business_rules():
    """CAT-FEAT-01 T1: RN-07 consta na tabela de regras de negócio."""
    rules = (Path(__file__).parents[3] / "docs" / "regras-de-negocio.md").read_text(
        encoding="utf-8"
    )

    assert "| RN-07 |" in rules


async def test_in_memory_bus_dispatches_by_event_type():
    bus = InMemoryBus()
    received = []

    async def handler(event):
        received.append(event)

    await bus.subscribe("orders", ["stock.reserved"], handler)
    await bus.publish(new_event(StockReserved(order_id="o1"), "catalog"))

    assert len(received) == 1
