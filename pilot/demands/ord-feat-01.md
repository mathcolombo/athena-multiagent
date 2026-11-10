---
id: ORD-FEAT-01
flow: orders
cycle: feature
title: cancelamento de pedido
issue: 4
---
Clientes pedem ao suporte para cancelar pedidos e hoje isso é impossível. Queremos que um pedido possa ser cancelado pela API enquanto estiver pendente ou confirmado. Pedidos já rejeitados ou cancelados não podem ser cancelados.

O cancelamento deve registrar o motivo informado e publicar um evento novo, `order.cancelled`, com o pedido, o cliente, os itens e o motivo. A devolução do estoque pelo catálogo fica para uma demanda futura.
