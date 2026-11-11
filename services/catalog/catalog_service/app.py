from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from skynet_events import (
    EventBus,
    EventEnvelope,
    OrderCreated,
    ProductCreated,
    ProductPriceChanged,
    StockRejected,
    StockLow,
    StockReserved,
    decode,
    new_event,
)

from catalog_service.db import CatalogDb

PRODUCER = "catalog"


class ProductCreate(BaseModel):
    name: str = Field(min_length=1)
    price_cents: int = Field(ge=0)
    stock: int = Field(ge=0)
    low_stock_threshold: int | None = Field(default=None, ge=0)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    price_cents: int | None = Field(default=None, ge=0)
    stock: int | None = Field(default=None, ge=0)
    low_stock_threshold: int | None = Field(default=None, ge=0)


def is_low_stock(product) -> bool:
    threshold = product["low_stock_threshold"]
    return threshold is not None and product["stock"] < threshold


def product_view(product) -> dict:
    data = dict(product)
    data["low_stock"] = is_low_stock(product)
    return data


def stock_low_event(product):
    return new_event(
        StockLow(
            product_id=product["id"],
            name=product["name"],
            stock=product["stock"],
            threshold=product["low_stock_threshold"],
        ),
        PRODUCER,
    )


def create_app(database_path: str, bus: EventBus) -> FastAPI:
    db = CatalogDb(database_path)

    async def on_order_created(event: EventEnvelope) -> None:
        if not db.mark_processed(str(event.event_id)):
            return
        order = decode(event, OrderCreated)
        reserved = db.reserve_stock([(item.product_id, item.quantity) for item in order.items])
        result = (
            StockReserved(order_id=order.order_id)
            if reserved
            else StockRejected(order_id=order.order_id, reason="estoque insuficiente")
        )
        await bus.publish(new_event(result, PRODUCER, event.correlation_id))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await bus.connect()
        await bus.subscribe("catalog", [OrderCreated.EVENT_TYPE], on_order_created)
        yield
        await bus.close()

    app = FastAPI(title="Skynet Catalog", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/products", status_code=201)
    async def create_product(body: ProductCreate) -> dict:
        product = db.create_product(
            body.name, body.price_cents, body.stock, body.low_stock_threshold
        )
        await bus.publish(
            new_event(
                ProductCreated(
                    product_id=product["id"],
                    name=product["name"],
                    price_cents=product["price_cents"],
                ),
                PRODUCER,
            )
        )
        if is_low_stock(product):
            await bus.publish(stock_low_event(product))
        return product_view(product)

    @app.get("/products")
    async def list_products() -> list[dict]:
        return [product_view(product) for product in db.list_products()]

    @app.get("/products/{product_id}")
    async def get_product(product_id: str) -> dict:
        product = db.get_product(product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="produto não encontrado")
        return product_view(product)

    @app.patch("/products/{product_id}")
    async def update_product(product_id: str, body: ProductUpdate) -> dict:
        previous = db.get_product(product_id)
        if previous is None:
            raise HTTPException(status_code=404, detail="produto não encontrado")
        old_price_cents = previous["price_cents"]
        product = db.update_product(
            product_id,
            body.name,
            body.price_cents,
            body.stock,
            body.low_stock_threshold,
            set_threshold="low_stock_threshold" in body.model_fields_set,
        )
        if body.price_cents is not None and body.price_cents != old_price_cents:
            await bus.publish(
                new_event(
                    ProductPriceChanged(
                        product_id=product_id,
                        old_price_cents=old_price_cents,
                        new_price_cents=body.price_cents,
                    ),
                    PRODUCER,
                )
            )
        if is_low_stock(product) and not is_low_stock(previous):
            await bus.publish(stock_low_event(product))
        return product_view(product)

    return app
