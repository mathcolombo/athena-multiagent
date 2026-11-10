import os

from skynet_events import RabbitMqBus

from cart_service.app import create_app

app = create_app(
    os.environ.get("DATABASE_PATH", "cart.db"),
    RabbitMqBus(os.environ["RABBITMQ_URL"]),
)
