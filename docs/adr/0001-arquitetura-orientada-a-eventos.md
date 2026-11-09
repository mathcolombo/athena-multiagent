# ADR 0001: serviços orientados a eventos com RabbitMQ

**Status:** aceito

## Contexto
Catálogo, carrinho e pedidos têm ciclos de mudança distintos e precisam evoluir sem acoplamento direto.

## Decisão
Um serviço por contexto delimitado, cada um com seu banco. A integração usa eventos em exchange topic do RabbitMQ, com fila durável por consumidor e dead-letter queue. A saga de pedido é coreografada, sem orquestrador central. Os contratos ficam em `libs/events`.

## Consequências
Há consistência eventual entre serviços, e consumidores precisam ser idempotentes. A biblioteca compartilhada de contratos é o único acoplamento em tempo de compilação.
