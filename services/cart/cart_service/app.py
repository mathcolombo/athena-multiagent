from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from skynet_events import (
    CartCheckedOut,
    EventBus,
    EventEnvelope,
    LineItem,
    ProductCreated,
    ProductPriceChanged,
    decode,
    new_event,
)

from cart_service.db import CartDb

PRODUCER = "cart"


class CartCreate(BaseModel):
    customer_id: str = Field(min_length=1)


class ItemSet(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)


def create_app(database_path: str, bus: EventBus) -> FastAPI:
    db = CartDb(database_path)

    async def on_product_event(event: EventEnvelope) -> None:
        if not db.mark_processed(str(event.event_id)):
            return
        if event.event_type == ProductCreated.EVENT_TYPE:
            product = decode(event, ProductCreated)
            db.upsert_snapshot(product.product_id, product.name, product.price_cents)
        else:
            change = decode(event, ProductPriceChanged)
            db.update_snapshot_price(change.product_id, change.new_price_cents)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await bus.connect()
        await bus.subscribe(
            "cart",
            [ProductCreated.EVENT_TYPE, ProductPriceChanged.EVENT_TYPE],
            on_product_event,
        )
        yield
        await bus.close()

    app = FastAPI(title="Skynet Cart", lifespan=lifespan)

    def open_cart_or_error(cart_id: str):
        cart = db.get_cart(cart_id)
        if cart is None:
            raise HTTPException(status_code=404, detail="carrinho não encontrado")
        if cart["status"] != "OPEN":
            raise HTTPException(status_code=409, detail="carrinho já finalizado")
        return cart

    def render(cart_id: str) -> dict:
        cart = db.get_cart(cart_id)
        items = [dict(item) for item in db.get_items(cart_id)]
        return {
            **dict(cart),
            "items": items,
            "total_cents": sum(i["unit_price_cents"] * i["quantity"] for i in items),
        }

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/carts", status_code=201)
    async def create_cart(body: CartCreate) -> dict:
        return render(db.create_cart(body.customer_id))

    @app.get("/carts/{cart_id}")
    async def get_cart(cart_id: str) -> dict:
        if db.get_cart(cart_id) is None:
            raise HTTPException(status_code=404, detail="carrinho não encontrado")
        return render(cart_id)

    @app.put("/carts/{cart_id}/items")
    async def set_item(cart_id: str, body: ItemSet) -> dict:
        open_cart_or_error(cart_id)
        if not db.has_snapshot(body.product_id):
            raise HTTPException(status_code=422, detail="produto desconhecido")
        db.set_item(cart_id, body.product_id, body.quantity)
        return render(cart_id)

    @app.delete("/carts/{cart_id}/items/{product_id}")
    async def remove_item(cart_id: str, product_id: str) -> dict:
        open_cart_or_error(cart_id)
        db.remove_item(cart_id, product_id)
        return render(cart_id)

    @app.post("/carts/{cart_id}/checkout")
    async def checkout(cart_id: str) -> dict:
        open_cart_or_error(cart_id)
        cart = render(cart_id)
        if not cart["items"]:
            raise HTTPException(status_code=422, detail="carrinho vazio")
        db.close_cart(cart_id)
        await bus.publish(
            new_event(
                CartCheckedOut(
                    cart_id=cart_id,
                    customer_id=cart["customer_id"],
                    items=[
                        LineItem(
                            product_id=item["product_id"],
                            quantity=item["quantity"],
                            unit_price_cents=item["unit_price_cents"],
                        )
                        for item in cart["items"]
                    ],
                    total_cents=cart["total_cents"],
                ),
                PRODUCER,
            )
        )
        return render(cart_id)

    return app
