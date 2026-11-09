from collections.abc import Awaitable, Callable, Iterable
from typing import Protocol

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from skynet_events.envelope import EventEnvelope

Handler = Callable[[EventEnvelope], Awaitable[None]]


class EventBus(Protocol):
    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    async def publish(self, event: EventEnvelope) -> None: ...

    async def subscribe(self, queue: str, event_types: Iterable[str], handler: Handler) -> None: ...


class InMemoryBus:
    """Barramento síncrono para testes; `deliver` simula a reentrega at-least-once do broker."""

    def __init__(self) -> None:
        self.published: list[EventEnvelope] = []
        self._subscriptions: list[tuple[set[str], Handler]] = []

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def publish(self, event: EventEnvelope) -> None:
        self.published.append(event)
        await self.deliver(event)

    async def deliver(self, event: EventEnvelope) -> None:
        for event_types, handler in self._subscriptions:
            if event.event_type in event_types:
                await handler(event)

    async def subscribe(self, queue: str, event_types: Iterable[str], handler: Handler) -> None:
        self._subscriptions.append((set(event_types), handler))


class RabbitMqBus:
    EXCHANGE = "skynet.events"
    DEAD_LETTER_EXCHANGE = "skynet.events.dlx"
    DEAD_LETTER_QUEUE = "skynet.dead-letters"

    def __init__(self, url: str) -> None:
        self._url = url
        self._connection = None
        self._channel = None
        self._exchange = None

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self._url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=1)
        self._exchange = await self._channel.declare_exchange(
            self.EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )
        dead_letters = await self._channel.declare_exchange(
            self.DEAD_LETTER_EXCHANGE, aio_pika.ExchangeType.FANOUT, durable=True
        )
        queue = await self._channel.declare_queue(self.DEAD_LETTER_QUEUE, durable=True)
        await queue.bind(dead_letters)

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()

    async def publish(self, event: EventEnvelope) -> None:
        message = aio_pika.Message(
            body=event.model_dump_json().encode(),
            message_id=str(event.event_id),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self._exchange.publish(message, routing_key=event.event_type)

    async def subscribe(self, queue: str, event_types: Iterable[str], handler: Handler) -> None:
        declared = await self._channel.declare_queue(
            queue,
            durable=True,
            arguments={"x-dead-letter-exchange": self.DEAD_LETTER_EXCHANGE},
        )
        for event_type in event_types:
            await declared.bind(self._exchange, routing_key=event_type)

        async def on_message(message: AbstractIncomingMessage) -> None:
            async with message.process(requeue=False):
                await handler(EventEnvelope.model_validate_json(message.body))

        await declared.consume(on_message)
