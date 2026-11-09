import pytest

from skynet_events import InMemoryBus, ProductPriceChanged, StockReserved, decode, new_event


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


async def test_in_memory_bus_dispatches_by_event_type():
    bus = InMemoryBus()
    received = []

    async def handler(event):
        received.append(event)

    await bus.subscribe("orders", ["stock.reserved"], handler)
    await bus.publish(new_event(StockReserved(order_id="o1"), "catalog"))

    assert len(received) == 1
