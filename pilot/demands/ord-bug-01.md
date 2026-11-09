---
id: ORD-BUG-01
flow: orders
cycle: bug
title: pedido duplicado após reentrega de evento
---
Chamado do suporte: depois de uma instabilidade de rede no RabbitMQ, alguns clientes ficaram com dois pedidos iguais para uma única finalização de carrinho, e o estoque foi baixado duas vezes.

Esperado: cada checkout gera exatamente um pedido, mesmo que o evento seja entregue mais de uma vez (RN-05). Observado: um pedido por entrega.
