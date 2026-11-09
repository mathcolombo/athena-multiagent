import os

from skynet_events import RabbitMqBus

from catalog_service.app import create_app

app = create_app(
    os.environ.get("DATABASE_PATH", "catalog.db"),
    RabbitMqBus(os.environ["RABBITMQ_URL"]),
)
