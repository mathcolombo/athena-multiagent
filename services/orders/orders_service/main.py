import os

from skynet_events import RabbitMqBus

from orders_service.app import create_app

app = create_app(
    os.environ.get("DATABASE_PATH", "orders.db"),
    RabbitMqBus(os.environ["RABBITMQ_URL"]),
)
