# Glossário de domínio

| Termo | Significado |
|---|---|
| Produto | Item vendável do catálogo, com preço em centavos e estoque |
| Snapshot de produto | Cópia local do produto mantida pelo carrinho a partir de eventos |
| Carrinho | Conjunto de itens de um cliente; `OPEN` ou `CHECKED_OUT` |
| Checkout | Finalização do carrinho, que publica `cart.checked_out` |
| Pedido | Resultado do checkout; `PENDING`, `CONFIRMED` ou `REJECTED` |
| Reserva de estoque | Baixa atômica de todos os itens do pedido, ou de nenhum |
| Saga | Sequência de eventos entre serviços que conclui um pedido |
| Envelope | Metadados do evento: `event_id`, `event_type`, `version`, `correlation_id`, `producer` |
| Entrega at-least-once | O broker pode entregar o mesmo evento mais de uma vez |
| Idempotência | Reprocessar o mesmo evento não muda o resultado |
