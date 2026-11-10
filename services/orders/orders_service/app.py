from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from skynet_events import (
    CartCheckedOut,
    EventBus,
    EventEnvelope,
    OrderConfirmed,
    OrderCreated,
    OrderRejected,
    StockRejected,
    StockReserved,
    decode,
    new_event,
)

from orders_service.db import OrdersDb

PRODUCER = "orders"


def create_app(database_path: str, bus: EventBus) -> FastAPI:
    db = OrdersDb(database_path)

    async def on_cart_checked_out(event: EventEnvelope) -> None:
        cart = decode(event, CartCheckedOut)
        order_id = db.create_order(
            cart.cart_id,
            cart.customer_id,
            [item.model_dump() for item in cart.items],
            cart.total_cents,
        )
        await bus.publish(
            new_event(
                OrderCreated(
                    order_id=order_id,
                    cart_id=cart.cart_id,
                    customer_id=cart.customer_id,
                    items=cart.items,
                    total_cents=cart.total_cents,
                ),
                PRODUCER,
                event.correlation_id,
            )
        )

    async def on_stock_reserved(event: EventEnvelope) -> None:
        if not db.mark_processed(str(event.event_id)):
            return
        order_id = decode(event, StockReserved).order_id
        if db.resolve_pending(order_id, "CONFIRMED"):
            await bus.publish(
                new_event(OrderConfirmed(order_id=order_id), PRODUCER, event.correlation_id)
            )

    async def on_stock_rejected(event: EventEnvelope) -> None:
        if not db.mark_processed(str(event.event_id)):
            return
        rejection = decode(event, StockRejected)
        if db.resolve_pending(rejection.order_id, "REJECTED", rejection.reason):
            await bus.publish(
                new_event(
                    OrderRejected(order_id=rejection.order_id, reason=rejection.reason),
                    PRODUCER,
                    event.correlation_id,
                )
            )

    handlers = {
        CartCheckedOut.EVENT_TYPE: on_cart_checked_out,
        StockReserved.EVENT_TYPE: on_stock_reserved,
        StockRejected.EVENT_TYPE: on_stock_rejected,
    }

    async def dispatch(event: EventEnvelope) -> None:
        await handlers[event.event_type](event)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await bus.connect()
        await bus.subscribe("orders", handlers.keys(), dispatch)
        yield
        await bus.close()

    app = FastAPI(title="Skynet Orders", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/orders")
    async def list_orders(customer_id: str | None = None) -> list[dict]:
        return db.list_orders(customer_id)

    @app.get("/orders/{order_id}")
    async def get_order(order_id: str) -> dict:
        order = db.get_order(order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="pedido não encontrado")
        return order

    return app
