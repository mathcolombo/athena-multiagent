from typing import ClassVar, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

from skynet_events.envelope import EventEnvelope


class EventPayload(BaseModel):
    EVENT_TYPE: ClassVar[str]
    VERSION: ClassVar[int] = 1


class LineItem(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)
    unit_price_cents: int = Field(ge=0)


class ProductCreated(EventPayload):
    EVENT_TYPE: ClassVar[str] = "product.created"

    product_id: str
    name: str
    price_cents: int


class ProductPriceChanged(EventPayload):
    EVENT_TYPE: ClassVar[str] = "product.price_changed"

    product_id: str
    old_price_cents: int
    new_price_cents: int


class CartCheckedOut(EventPayload):
    EVENT_TYPE: ClassVar[str] = "cart.checked_out"

    cart_id: str
    customer_id: str
    items: list[LineItem]
    total_cents: int


class OrderCreated(EventPayload):
    EVENT_TYPE: ClassVar[str] = "order.created"

    order_id: str
    cart_id: str
    customer_id: str
    items: list[LineItem]
    total_cents: int


class OrderConfirmed(EventPayload):
    EVENT_TYPE: ClassVar[str] = "order.confirmed"

    order_id: str


class OrderRejected(EventPayload):
    EVENT_TYPE: ClassVar[str] = "order.rejected"

    order_id: str
    reason: str


class StockReserved(EventPayload):
    EVENT_TYPE: ClassVar[str] = "stock.reserved"

    order_id: str


class StockRejected(EventPayload):
    EVENT_TYPE: ClassVar[str] = "stock.rejected"

    order_id: str
    reason: str


class StockLow(EventPayload):
    EVENT_TYPE: ClassVar[str] = "stock.low"

    product_id: str
    name: str
    stock: int
    threshold: int


P = TypeVar("P", bound=EventPayload)


def new_event(
    payload: EventPayload, producer: str, correlation_id: UUID | None = None
) -> EventEnvelope:
    fields = {
        "event_type": payload.EVENT_TYPE,
        "version": payload.VERSION,
        "producer": producer,
        "payload": payload.model_dump(mode="json"),
    }
    if correlation_id is not None:
        fields["correlation_id"] = correlation_id
    return EventEnvelope(**fields)


def decode(event: EventEnvelope, payload_type: type[P]) -> P:
    if event.event_type != payload_type.EVENT_TYPE:
        raise ValueError(f"esperado {payload_type.EVENT_TYPE}, recebido {event.event_type}")
    return payload_type.model_validate(event.payload)
